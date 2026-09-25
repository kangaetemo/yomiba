"""ImportService: maps normalized ``SearchResult`` objects into database
entities with deterministic, constraint-backed deduplication.

This is the ONLY place where scraper results become rows. Scrapers never
touch the database; route handlers never contain this logic.

**Catalog-only policy (task 5):** the app serves only the tracked (mangakol)
catalog, so a store import may only enrich series that ALREADY EXIST in the
catalog manifest:

* a product matching no existing catalog series is **skipped** — a store
  import never creates Series (or Publisher) rows;
* existing catalog series keep receiving new volumes, listings and price
  history (that is how a catalog manga's new volume gets listed);
* the ISBN / edition matching rules are unchanged — they simply never fall
  through to a creation step anymore.

Resolution priorities (strongest first):
  1. ISBN          -> globally unique; the same ISBN is the same physical
                      book, so it always resolves to a single Volume
                      (which must belong to a catalog series; otherwise skip)
  2. series + volume number (within the resolved catalog series)
  3. series chosen by normalized title when no publisher is available
                      (only when exactly one catalog series matches;
                      otherwise skip — never guess, never create)

A failing scraper is isolated: its error is recorded in the report and the
import continues with the remaining stores.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import (
    CatalogSeries,
    PriceHistory,
    Publisher,
    PublisherAlias,
    Series,
    Store,
    StoreListing,
    Volume,
)
from ..normalization import (
    normalize_isbn,
    normalize_publisher,
    normalize_text,
    parse_volume_title,
)
from ..normalization.volume import UNNUMBERED_VOLUME
from ..scrapers import SearchResult
from ..scrapers.registry import get_scrapers
from ..scrapers.base import BaseScraper
from ..utils import from_cents, to_cents, utcnow

logger = logging.getLogger("yomiba.import")

#: Reserved publisher used when a result carries no publisher information and
#: the edition cannot be determined unambiguously. It keeps unknown items
#: isolated from real editions instead of corrupting them.
UNKNOWN_PUBLISHER = "Bilinmiyor"


class ImportAction(str, Enum):
    CREATED = "created"
    UPDATED = "updated"
    SKIPPED = "skipped"


@dataclass
class StoreImportResult:
    store_code: str
    store_name: str
    results_found: int = 0
    created: int = 0
    updated: int = 0
    skipped: int = 0
    errors: int = 0
    #: Set when the scraper itself failed (transport / parse / block).
    error: str | None = None


@dataclass
class ImportReport:
    query: str
    started_at: datetime
    finished_at: datetime | None = None
    stores: list[StoreImportResult] = field(default_factory=list)

    @property
    def total_created(self) -> int:
        return sum(s.created for s in self.stores)

    @property
    def total_updated(self) -> int:
        return sum(s.updated for s in self.stores)

    @property
    def total_skipped(self) -> int:
        return sum(s.skipped for s in self.stores)

    @property
    def total_errors(self) -> int:
        return sum(s.errors for s in self.stores)


class ImportService:
    """Coordinates scraping + entity resolution for one or more stores."""

    def __init__(
        self,
        session: Session,
        *,
        scrapers: list[BaseScraper] | None = None,
    ) -> None:
        self.session = session
        #: Optional pre-built scraper list (used by tests). When omitted,
        #: scrapers are instantiated from the registry per import run.
        self.scrapers = scrapers

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run_import(
        self, query: str, store_ids: list[str] | None = None
    ) -> ImportReport:
        """Run every (selected) scraper for ``query`` and import the results.

        Scraper failures are isolated and reported; a bad result never stops
        the rest of the run.

        Multi-printing handling: a store may list several printings of the
        same volume (different ISBNs at different prices). Results are first
        resolved to their (volume, store) target and grouped per target; only
        the cheapest priced printing of each group is imported. Without this
        the listing's price would flip between the printings on every check,
        fabricating price history and fake drops.
        """
        report = ImportReport(query=query, started_at=utcnow())
        scrapers = self.scrapers if self.scrapers is not None else get_scrapers(store_ids)

        for scraper in scrapers:
            store_report = StoreImportResult(
                store_code=scraper.store_id, store_name=scraper.store_name
            )
            report.stores.append(store_report)

            try:
                with scraper:
                    results = scraper.search(query)
                store_report.results_found = len(results)
                if scraper.stats:
                    logger.info(
                        "import: %s search stats for %r: %s",
                        scraper.store_id,
                        query,
                        scraper.stats,
                    )
            except Exception as exc:  # noqa: BLE001 - isolation by design
                logger.exception(
                    "import: scraper %s failed for query %r", scraper.store_id, query
                )
                store_report.error = f"{type(exc).__name__}: {exc}"
                continue

            # Phase 1: resolve every result to its (volume, store) target.
            groups: dict[tuple[int, int], list[tuple[int | None, SearchResult]]] = {}
            for result in results:
                try:
                    target = self._resolve_target(result)
                    # Commit resolution side effects (new store/volume rows,
                    # ISBN enrichment) right away so a later failing result's
                    # rollback cannot undo them — same isolation semantics as
                    # the original per-result loop.
                    self.session.commit()
                except Exception:  # noqa: BLE001 - per-result isolation
                    logger.exception(
                        "import: failed to resolve %r from %s",
                        result.title,
                        scraper.store_id,
                    )
                    self.session.rollback()
                    store_report.errors += 1
                    continue
                if target is None:
                    store_report.skipped += 1
                    continue
                volume, store = target
                groups.setdefault((volume.id, store.id), []).append(
                    (to_cents(result.price), result)
                )

            # Phase 2: import one representative per (volume, store) group —
            # the cheapest priced printing wins; unpriced ones never hide a
            # priced one.
            for (volume_id, store_id), items in groups.items():
                priced = [(p, r) for p, r in items if p is not None]
                best = min(priced, key=lambda t: t[0])[1] if priced else items[0][1]
                if len(items) > 1:
                    logger.info(
                        "import: %d printings of the same volume at %s for %r; "
                        "keeping the cheapest (₺%s)",
                        len(items),
                        scraper.store_name,
                        best.title,
                        from_cents(to_cents(best.price)),
                    )
                    store_report.skipped += len(items) - 1
                volume = self.session.get(Volume, volume_id)
                store = self.session.get(Store, store_id)
                try:
                    action = self._upsert_listing(volume, store, best)
                    self.session.commit()
                except Exception:  # noqa: BLE001 - per-group isolation
                    logger.exception(
                        "import: failed to import %r from %s",
                        best.title,
                        scraper.store_id,
                    )
                    self.session.rollback()
                    store_report.errors += 1
                    continue
                if action is ImportAction.CREATED:
                    store_report.created += 1
                elif action is ImportAction.UPDATED:
                    store_report.updated += 1
                else:
                    store_report.skipped += 1

        report.finished_at = utcnow()
        return report

    def import_result(self, result: SearchResult) -> ImportAction:
        """Import one normalized result. Caller commits/rolls back.

        Note: this imports the result on its own — multi-printing dedup
        (cheapest printing wins per (volume, store)) applies to results that
        go through run_import, which is how all production imports work.
        """
        target = self._resolve_target(result)
        if target is None:
            return ImportAction.SKIPPED
        volume, store = target
        return self._upsert_listing(volume, store, result)

    def _resolve_target(
        self, result: SearchResult
    ) -> tuple[Volume, Store] | None:
        """Resolve a result to the (volume, store) it would import into.

        Returns None (with a log line) when the result must be skipped: no
        title/url, collection, no derivable series, no matching catalog
        series, or an ISBN outside the catalog. Never writes listings; may
        create the target volume via _resolve_volume — the caller commits or
        rolls back as usual.
        """
        title = (result.title or "").strip()
        if not title or not result.product_url:
            logger.debug("import: skipping result without title/url: %r", result.title)
            return None

        parsed = parse_volume_title(title)
        if parsed.is_collection:
            logger.debug("import: skipping collection %r", title)
            return None

        series_raw = result.series_title or parsed.base_title
        series_key = normalize_text(series_raw)
        if not series_key:
            logger.debug("import: cannot derive series title from %r", title)
            return None

        if result.volume_number is not None:
            volume_number = result.volume_number
        elif parsed.volume_number is not None:
            volume_number = parsed.volume_number
        else:
            volume_number = UNNUMBERED_VOLUME

        store = self._resolve_store(result.store_id, result.store_name)
        isbn = normalize_isbn(result.isbn)

        # ISBN is the strongest identity: when it already resolves to a
        # volume, that volume's Series/Publisher identity wins and the
        # (possibly conflicting) metadata on this result must NOT create
        # phantom Publisher/Series rows. Catalog-only: the volume must
        # belong to a catalog series; an ISBN outside the catalog skips.
        if isbn:
            volume = self.session.scalar(select(Volume).where(Volume.isbn == isbn))
            if volume is not None:
                if not self._series_is_catalog(volume.series_id):
                    logger.info(
                        "import: skipping %r — ISBN %s resolves outside the catalog",
                        title,
                        isbn,
                    )
                    return None
                self._backfill_cover(volume, result)
                return (volume, store)

        # Read-only publisher resolution: a store import never creates
        # Publisher rows (catalog-only).
        publisher_name = (result.publisher or "").strip()
        if publisher_name:
            publisher = self._find_publisher(publisher_name)
            if publisher is not None:
                series = self._resolve_series_for_publisher(publisher, series_key)
            else:
                # Unknown publisher claim: only the bilingual bridge
                # (title-based, unambiguous identity) is trusted. A plain
                # title match must NOT merge this product into a different
                # edition that happens to be the catalog's only candidate.
                series = self._find_series_by_bilingual_key(series_key)
        else:
            series = self._resolve_series_no_publisher(series_key)

        if series is None:
            logger.info(
                "import: skipping %r — no existing catalog series (catalog-only)",
                title,
            )
            return None
        volume = self._resolve_volume(series, isbn, volume_number, result)
        return (volume, store)

    # ------------------------------------------------------------------
    # Entity resolution
    # ------------------------------------------------------------------
    def _resolve_store(self, store_code: str, store_name: str) -> Store:
        store = self.session.scalar(select(Store).where(Store.code == store_code))
        if store is not None:
            return store
        # Defensive: a scraper should always point at a seeded store, but if a
        # new store shows up we create it deterministically (unique code).
        existing_by_name = self.session.scalar(select(Store).where(Store.name == store_name))
        if existing_by_name is not None:
            return existing_by_name
        store = Store(code=store_code, name=store_name)
        self.session.add(store)
        self.session.flush()
        logger.info("import: created store %r (%s)", store_name, store_code)
        return store

    def _find_publisher(self, raw_name: str | None) -> Publisher | None:
        """READ-ONLY publisher lookup (catalog-only: imports never create
        Publisher rows). Resolves an existing row by normalized name or via
        a known spelling-variant alias (data-driven, see publisher_aliases).
        """
        if not raw_name or not raw_name.strip():
            return None
        key = normalize_publisher(raw_name)
        if not key:
            return None
        publisher = self.session.scalar(
            select(Publisher).where(Publisher.normalized_name == key)
        )
        if publisher is not None:
            return publisher
        alias = self.session.scalar(
            select(PublisherAlias).where(PublisherAlias.normalized_alias == key)
        )
        if alias is not None:
            target = self.session.get(Publisher, alias.publisher_id)
            if target is not None:
                logger.info(
                    "import: resolved publisher %r via alias -> %r",
                    raw_name.strip(),
                    target.name,
                )
                return target
        return None

    def _series_is_catalog(self, series_id: int) -> bool:
        return (
            self.session.scalar(
                select(CatalogSeries.series_id).where(
                    CatalogSeries.series_id == series_id
                )
            )
            is not None
        )

    def _resolve_series_for_publisher(
        self, publisher: Publisher, series_key: str
    ) -> Series | None:
        """Edition identity: (publisher, normalized title), catalog-only.
        Falls back to the bilingual bridge before skipping."""
        series = self.session.scalar(
            select(Series).where(
                Series.publisher_id == publisher.id,
                Series.normalized_title == series_key,
                Series.id.in_(select(CatalogSeries.series_id).distinct()),
            )
        )
        if series is not None:
            return series
        # Bilingual bridge: "One Punch Man 3 - Tek Yumruk" carries both
        # titles of an existing (catalog) series.
        return self._find_series_by_bilingual_key(series_key)

    def _resolve_series_no_publisher(self, series_key: str) -> Series | None:
        """No publisher information: use the single unambiguous catalog
        edition when there is exactly one; otherwise the bilingual bridge;
        otherwise None (never guess between editions, never create)."""
        candidates = self.session.scalars(
            select(Series).where(
                Series.normalized_title == series_key,
                Series.id.in_(select(CatalogSeries.series_id).distinct()),
            )
        ).all()
        if len(candidates) == 1:
            return candidates[0]
        return self._find_series_by_bilingual_key(series_key)

    def _find_series_by_bilingual_key(self, series_key: str) -> Series | None:
        """Bridge for bilingual product titles.

        Turkish stores commonly sell manga under "Original Title - Local
        Title" (e.g. "One Punch Man 3 - Tek Yumruk"). A product key that
        equals EXACTLY the concatenation of one series' original and local
        normalized titles (either order) — or the original title alone —
        identifies that series unambiguously.

        Deliberately strict: full-key equality only (no prefixes, no fuzzy
        matching — "tokyo ghoul re" must not bridge into "Tokyo Gül"), both
        title parts must be present on the series, and if more than one
        series matches the bridge is skipped (never guess). Catalog-only:
        only catalog series are eligible bridge targets.
        """
        catalog_ids = select(CatalogSeries.series_id).distinct()
        candidates: set[int] = set()
        for s in self.session.scalars(
            select(Series).where(
                Series.original_title.isnot(None), Series.id.in_(catalog_ids)
            )
        ):
            if not s.original_title or not s.normalized_title:
                continue
            if series_key in (
                f"{s.original_title} {s.normalized_title}",
                f"{s.normalized_title} {s.original_title}",
            ):
                candidates.add(s.id)
        if not candidates:
            for s in self.session.scalars(
                select(Series).where(
                    Series.original_title == series_key, Series.id.in_(catalog_ids)
                )
            ):
                candidates.add(s.id)
        if len(candidates) == 1:
            return self.session.get(Series, candidates.pop())
        return None

    def _resolve_volume(
        self,
        series: Series,
        isbn: str | None,
        volume_number: int,
        result: SearchResult,
    ) -> Volume:
        # 1) ISBN is the strongest cross-store identifier: globally unique.
        if isbn:
            volume = self.session.scalar(select(Volume).where(Volume.isbn == isbn))
            if volume is not None:
                self._backfill_cover(volume, result)
                return volume

        # 2) series + volume number (the edition-aware dedup key).
        volume = self.session.scalar(
            select(Volume).where(
                Volume.series_id == series.id,
                Volume.volume_number == volume_number,
            )
        )
        if volume is not None:
            if isbn and volume.isbn is None:
                volume.isbn = isbn  # enrich the existing volume
            elif isbn and volume.isbn != isbn:
                logger.warning(
                    "import: ISBN conflict for volume %s (series %s, no %s): "
                    "keeping %s, ignoring %s",
                    volume.id,
                    series.id,
                    volume_number,
                    volume.isbn,
                    isbn,
                )
            self._backfill_cover(volume, result)
            return volume

        # 3) Create a new volume in the resolved series.
        volume = Volume(
            series_id=series.id,
            volume_number=volume_number,
            isbn=isbn,
            cover_url=result.image_url,
        )
        self.session.add(volume)
        self.session.flush()
        logger.info(
            "import: created volume series=%s number=%s isbn=%s",
            series.id,
            volume_number,
            isbn,
        )
        return volume

    @staticmethod
    def _backfill_cover(volume: Volume, result: SearchResult) -> None:
        if volume.cover_url is None and result.image_url:
            volume.cover_url = result.image_url

    # ------------------------------------------------------------------
    # Listing upsert + price history
    # ------------------------------------------------------------------
    def _upsert_listing(
        self, volume: Volume, store: Store, result: SearchResult
    ) -> ImportAction:
        now = utcnow()
        price_cents = to_cents(result.price)

        listing = self.session.scalar(
            select(StoreListing).where(
                StoreListing.volume_id == volume.id,
                StoreListing.store_id == store.id,
            )
        )

        if listing is None:
            listing = StoreListing(
                volume_id=volume.id,
                store_id=store.id,
                product_url=result.product_url,
                price=price_cents,
                in_stock=result.in_stock,
                last_checked=now,
                image_url=result.image_url,
            )
            self.session.add(listing)
            self.session.flush()
            if price_cents is not None:
                self.session.add(
                    PriceHistory(listing_id=listing.id, price=price_cents, checked_at=now)
                )
            return ImportAction.CREATED

        price_changed = price_cents is not None and listing.price != price_cents
        if price_cents is not None:
            listing.price = price_cents
        listing.in_stock = result.in_stock
        listing.product_url = result.product_url
        listing.last_checked = now
        if result.image_url and not listing.image_url:
            listing.image_url = result.image_url

        if price_changed:
            self.session.add(
                PriceHistory(listing_id=listing.id, price=listing.price, checked_at=now)
            )
        return ImportAction.UPDATED
