"""ImportService: maps normalized ``SearchResult`` objects into database
entities with deterministic, constraint-backed deduplication.

This is the ONLY place where scraper results become rows. Scrapers never
touch the database; route handlers never contain this logic.

**Catalog-only policy (task 5):** the app serves only the tracked (mangakol)
catalog, so a store import may only enrich series that ALREADY EXIST in the
catalog manifest:

* a product matching no existing catalog series is **skipped** — a store
  import never creates Series (or Publisher) rows;
* existing positive catalog volumes receive listings and price history;
* missing volumes and conflicting ISBNs are rejected. A store never creates
  Volume identities; catalog sync owns them.

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
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
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
from ..scrapers import SearchResult
from ..scrapers.registry import get_scrapers
from ..scrapers.base import BaseScraper
from ..scrapers.relevance import check_manga_relevance
from ..utils import from_cents, to_cents, utcnow

logger = logging.getLogger("yomiba.import")

#: Reserved publisher used when a result carries no publisher information and
#: the edition cannot be determined unambiguously. It keeps unknown items
#: isolated from real editions instead of corrupting them.
UNKNOWN_PUBLISHER = "Bilinmiyor"

#: Separate editions that must never attach to a normal catalog volume.
_EDITION_CONFLICT_RE = r"\b(?:omnibus|hardcover|collector|special edition|ozel baski)\b"
#: Remainder (after a catalog title prefix) that is a plain volume token.
_REMAINDER_VOLUME_RE = re.compile(
    r"(?:(?:cilt|c|vol|volume|bant|sayi|no)\s*)?0*(\d{1,3})(?:\s*(?:cilt|c))?"
)
_REMAINDER_COLLECTION_RE = re.compile(
    r"\b(?:box|set|seti|kutu|bundle|toplu|koleksiyon|collection|complete|deluxe)\b|\b\d{1,3}\s+\d{1,3}\b"
)


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
    reasons: dict[str, int] = field(default_factory=dict)


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
        self.last_reason: str | None = None

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
        the cheapest priced in-stock printing of each group is imported
        (falling back to unavailable products if none are in stock). Without this
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
                    reason = self.last_reason or "no_series_match"
                    store_report.reasons[reason] = store_report.reasons.get(reason, 0) + 1
                    continue
                volume, store = target
                groups.setdefault((volume.id, store.id), []).append(
                    (to_cents(result.price), result)
                )

            # Phase 2: import one representative per (volume, store) group —
            # prefer available products, then the cheapest priced printing.
            for (volume_id, store_id), items in groups.items():
                available = [(p, r) for p, r in items if r.in_stock] or items
                priced = [(p, r) for p, r in available if p is not None]
                best = min(priced, key=lambda t: t[0])[1] if priced else available[0][1]
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
                    store_report.reasons["duplicate"] = store_report.reasons.get("duplicate", 0) + len(items) - 1
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
                    reason = self.last_reason or "skipped"
                    store_report.reasons[reason] = store_report.reasons.get(reason, 0) + 1

            logger.info("import matching summary: store=%s results=%d matched=%d rejected=%s errors=%d",
                        store_report.store_code, store_report.results_found,
                        store_report.created + store_report.updated, store_report.reasons, store_report.errors)
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
        enrich ISBN/cover on an existing target — the caller commits or
        rolls back as usual.
        """
        self.last_reason = None
        #: Non-catalog volume that holds this result's ISBN (legacy store
        #: data); resolution may continue only for the SAME work.
        self._non_catalog_holder = None
        title = (result.title or "").strip()
        if not title or not result.product_url:
            return self._reject("invalid_result")

        if not check_manga_relevance(title=title, publisher=result.publisher, isbn=result.isbn,
                                     category=result.category).accept:
            return self._reject("non_book_product")

        parsed = parse_volume_title(title)
        if re.search(_EDITION_CONFLICT_RE, normalize_text(title)):
            return self._reject("edition_conflict")
        if parsed.is_collection:
            # "Kaiju No: 8 - 8 No'lu Canavar 3" looks like a "8 - 8" range
            # only because the catalog title itself contains numbers.
            return self._catalog_title_fallback(result, "box_set")

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
            volume_number = None

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
                    # Legacy store-created (non-catalog) row holds the ISBN.
                    # A DIFFERENT work stays rejected (the ISBN proves the
                    # product is that work). A same-title duplicate — e.g. the
                    # pre-catalog importer's own "One Piece" series next to
                    # the Mangakol catalog "One Piece" — must not starve the
                    # catalog edition: resolve by title/number below and
                    # verify it is the same work before importing. The ISBN
                    # is never moved (unique).
                    logger.info(
                        "import: ISBN %s is held by non-catalog volume %s; "
                        "resolving %r by title (same work only)",
                        isbn, volume.id, title,
                    )
                    self._non_catalog_holder = volume
                    isbn = None
                elif volume.volume_number < 0:
                    # Legacy phantom (old import bug) still holds this ISBN.
                    # It is not a catalog identity: never attach to it, and
                    # never move/copy the ISBN (unique). Resolve the product
                    # by title/number like an ISBN-less result instead, so
                    # the real catalog volume is no longer starved.
                    logger.info(
                        "import: ISBN %s is held by legacy phantom volume %s; "
                        "resolving %r without ISBN",
                        isbn, volume.id, title,
                    )
                    isbn = None
                else:
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
                # An unrecognized publisher cannot prove edition identity.
                series = None
        else:
            series = self._resolve_series_no_publisher(series_key)

        if series is None and series_key.endswith(" manga") and parsed.volume_number is not None:
            # A store's generic suffix is only a secondary exact key. Never
            # use prefix/fuzzy matching or drop edition words.
            shorter = series_key.removesuffix(" manga")
            if publisher_name:
                series = self._resolve_series_for_publisher(publisher, shorter) if publisher else None
            else:
                series = self._resolve_series_no_publisher(shorter)
        if series is None:
            if self._non_catalog_holder is not None:
                return self._reject("non_catalog_volume")
            if parsed.evidence in {"numeric_metadata", "ambiguous_numbers"}:
                reason = "ambiguous_volume"
            else:
                reason = "publisher_conflict" if publisher_name else "no_series_match"
            return self._catalog_title_fallback(result, reason)
        if result.volume_number is not None and parsed.volume_number is not None and result.volume_number != parsed.volume_number:
            return self._reject("ambiguous_volume")
        if parsed.evidence in {"numeric_metadata", "ambiguous_numbers"}:
            return self._reject("ambiguous_volume")
        if not self._same_work_as_holder(series, volume_number):
            return self._reject("non_catalog_volume")
        volume = self._resolve_volume(series, isbn, volume_number, result)
        if volume is None:
            return None
        return (volume, store)

    def _catalog_title_fallback(self, result: SearchResult, reason: str):
        """Second chance for catalog titles the generic parser misreads.

        The generic parser cannot tell "Mob Psycho 100 Cilt 2", "Dövüş Sınıfı
        3 Cilt 2", "Disney Manga - 6 Süper Kahraman", "Kaiju No: 8 - 8 No'lu
        Canavar 3" or "Mavi Kutu 4" (collection word in the title) apart from
        volume numbers, ranges or box sets. Runs only after the normal path
        rejected the product. The product title must START with the exact
        normalized title of a catalog series; only the remainder is parsed,
        and it must be empty or a plain volume token ("3", "cilt 3", "3 cilt")
        with no collection words or ranges.
        Anything else keeps the original rejection ``reason``. Never creates
        rows and never guesses between editions.
        """
        title_key = normalize_text(result.title)
        remainder_number = None
        match = self._catalog_series_prefix(title_key, (result.publisher or "").strip())
        if match is None:
            return self._reject(reason)
        series, remainder = match
        if remainder:
            if _REMAINDER_COLLECTION_RE.search(remainder):
                return self._reject("box_set")
            token = _REMAINDER_VOLUME_RE.fullmatch(remainder)
            if token is None:
                return self._reject(reason)
            remainder_number = int(token.group(1))
        store = self._resolve_store(result.store_id, result.store_name)
        isbn = normalize_isbn(result.isbn)
        if isbn:
            holder = self.session.scalar(select(Volume).where(Volume.isbn == isbn))
            if holder is not None and not self._series_is_catalog(holder.series_id):
                self._non_catalog_holder = holder
                isbn = None
            elif holder is not None and holder.volume_number < 0:
                isbn = None  # legacy phantom keeps it; see _resolve_target
        if not self._same_work_as_holder(series, remainder_number):
            return self._reject("non_catalog_volume")
        volume = self._resolve_volume(series, isbn, remainder_number, result, title_verified=True)
        if volume is None:
            return None
        logger.info("import: %r matched catalog title %r by prefix", result.title, series.title)
        return (volume, store)

    def _catalog_series_prefix(self, title_key: str, publisher_name: str):
        """Longest catalog series title that prefixes ``title_key`` at a word
        boundary; returns ``(series, remainder)`` or None."""
        if not title_key:
            return None
        publisher_id = None
        if publisher_name:
            publisher = self._find_publisher(publisher_name)
            if publisher is None:
                return None
            publisher_id = publisher.id
        query = select(Series).where(
            Series.id.in_(select(CatalogSeries.series_id).distinct()),
            Series.normalized_title.isnot(None),
        )
        if publisher_id is not None:
            query = query.where(Series.publisher_id == publisher_id)
        best: list[Series] = []
        best_len = 0
        for series in self.session.scalars(query):
            key = series.normalized_title or ""
            if not key:
                continue
            if title_key != key and not title_key.startswith(key + " "):
                continue
            if len(key) > best_len:
                best, best_len = [series], len(key)
            elif len(key) == best_len:
                best.append(series)
        if len(best) != 1:
            return None
        return best[0], title_key[best_len:].strip()

    def _same_work_as_holder(self, series: Series, volume_number: int | None) -> bool:
        """True unless a non-catalog row holds the ISBN for a DIFFERENT work.

        Same work = the holder's series has the catalog series' normalized
        title (or its original title) AND the holder's volume number agrees
        (unknown/-1 on either side is not a contradiction).
        """
        holder = self._non_catalog_holder
        if holder is None:
            return True
        holder_series = self.session.get(Series, holder.series_id)
        titles = {series.normalized_title}
        if series.original_title:
            titles.add(series.original_title)
        if holder_series is None or holder_series.normalized_title not in titles:
            return False
        if holder.volume_number < 0 or volume_number is None:
            return True
        return holder.volume_number == volume_number

    def _reject(self, reason: str):
        self.last_reason = reason
        return None

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
        return self._find_series_by_bilingual_key(series_key, publisher_id=publisher.id)

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

    def _find_series_by_bilingual_key(
        self, series_key: str, *, publisher_id: int | None = None
    ) -> Series | None:
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
        publisher_filter = [] if publisher_id is None else [Series.publisher_id == publisher_id]
        candidates: set[int] = set()
        for s in self.session.scalars(
            select(Series).where(
                Series.original_title.isnot(None),
                Series.id.in_(catalog_ids),
                *publisher_filter,
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
                    Series.original_title == series_key,
                    Series.id.in_(catalog_ids),
                    *publisher_filter,
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
        volume_number: int | None,
        result: SearchResult,
        *,
        title_verified: bool = False,
    ) -> Volume | None:
        # 1) ISBN is the strongest cross-store identifier: globally unique.
        if isbn:
            volume = self.session.scalar(select(Volume).where(Volume.isbn == isbn))
            if volume is not None:
                if not self._series_is_catalog(volume.series_id):
                    return self._reject("non_catalog_volume")
                self._backfill_cover(volume, result)
                return volume

        # Unknown products cannot create a catalog identity. Only a series
        # with exactly one positive volume, numbered 1, can use this fallback.
        if volume_number is None and not title_verified:
            title_key = normalize_text(parse_volume_title(result.title).base_title)
            allowed_titles = {series.normalized_title}
            if series.original_title:
                allowed_titles.update({series.original_title,
                    f"{series.original_title} {series.normalized_title}",
                    f"{series.normalized_title} {series.original_title}"})
            if title_key not in allowed_titles:
                return self._reject("ambiguous_volume")
        if volume_number is None:
            real = self.session.scalars(select(Volume).where(
                Volume.series_id == series.id, Volume.volume_number >= 0,
            )).all()
            if len(real) != 1 or real[0].volume_number != 1:
                return self._reject("no_volume_number")
            volume_number = 1
        if volume_number < 0:
            return self._reject("no_volume_number")

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
                return self._reject("isbn_conflict")
            self._backfill_cover(volume, result)
            return volume

        return self._reject("volume_not_found")

    @staticmethod
    def _may_switch_product(
        listing: StoreListing, result: SearchResult, price_cents: int | None, now: datetime
    ) -> bool:
        # Never replace an available offer with an unavailable product;
        # keep the identity stable when both are unavailable, even if stale.
        if not result.in_stock:
            return False
        if not listing.in_stock:
            return True
        last = listing.last_checked
        if last is None:
            return True
        if last.tzinfo is None:
            last = last.replace(tzinfo=timezone.utc)
        window = timedelta(hours=get_settings().listing_product_switch_hours)
        if now - last >= window:
            return True
        return price_cents is not None and (listing.price is None or price_cents < listing.price)

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
        # Final write boundary: every resolution path must remain catalog-only.
        if not self._series_is_catalog(volume.series_id):
            self.last_reason = "non_catalog_volume"
            return ImportAction.SKIPPED
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

        product_changed = listing.product_url != result.product_url
        if product_changed and not self._may_switch_product(
            listing, result, price_cents, now
        ):
            # A different product of the same store resolved to this volume
            # (another printing / edition). Switching back and forth between
            # products across import runs fabricates price history and fake
            # drops. Only an in-stock candidate may replace it, using the
            # stock / price / freshness policy above.
            self.last_reason = "other_product"
            logger.info(
                "import: keeping listing %s on %s; ignoring other product %s",
                listing.id, listing.product_url, result.product_url,
            )
            return ImportAction.SKIPPED

        # A product switch is not a price change of the old product. Keep
        # existing history, but do not fabricate a transition on the switch.
        # Subsequent same-product changes use the new product's price.
        price_changed = not product_changed and price_cents is not None and listing.price != price_cents
        if price_cents is not None or product_changed:
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
