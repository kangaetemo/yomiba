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
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import Enum

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    CatalogSeries,
    ListingExclusion,
    PriceHistory,
    Publisher,
    PublisherAlias,
    Series,
    Store,
    StoreListing,
    Volume,
)
from ..normalization.isbn import book_isbn, is_foreign_isbn, is_foreign_language
from ..normalization import (
    normalize_isbn,
    normalize_publisher,
    normalize_text,
    parse_volume_range,
    parse_volume_title,
    publisher_family_key,
)
from ..scrapers import SearchResult
from ..scrapers.registry import get_scrapers
from ..scrapers.base import BaseScraper
from ..scrapers.common import FOREIGN_PUBLISHER_RE
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
# A dash used as a title separator: at least one space next to it, so
# hyphenated words ("Tamon-Kun") are never split.
_DASH_SEPARATOR_RE = re.compile(r"\s+[-\u2013\u2014]\s*|\s*[-\u2013\u2014]\s+")
_CILT_NUMBER_RE = re.compile(r"\bcilt\s*0*(\d{1,3})\b")
#: "Warcraft - Efsaneler (Birinci Kitap)": a spelled-out ordinal volume.
_ORDINAL_WORDS = {
    "birinci": 1, "ikinci": 2, "ucuncu": 3, "dorduncu": 4, "besinci": 5,
    "altinci": 6, "yedinci": 7, "sekizinci": 8, "dokuzuncu": 9, "onuncu": 10,
}
_REMAINDER_ORDINAL_RE = re.compile(
    r"(" + "|".join(_ORDINAL_WORDS) + r")\s+(?:kitap|cilt)"
)
#: Catalog-title subtitle separators: a spaced dash or a colon
#: ("Zom 100: Ölülerin Yapılacaklar Listesi").
_SUBTITLE_SEPARATOR_RE = re.compile(_DASH_SEPARATOR_RE.pattern + r"|\s*:\s+")
_REMAINDER_COLLECTION_RE = re.compile(
    r"\b(?:box|set|seti|kutu|bundle|toplu|koleksiyon|collection|complete|deluxe)\b|\b\d{1,3}\s+\d{1,3}\b"
)


_FOREIGN_PUBLISHER_RE = FOREIGN_PUBLISHER_RE
#: English volume wording: "Vol. 5", "Vol 5", "Volume 3".
_ENGLISH_VOLUME_RE = re.compile(r"\bvol(?:ume|\.)?\s*\d", re.IGNORECASE)


def _aware(value: datetime) -> datetime:
    """SQLite returns naive datetimes; they are stored as UTC."""
    return value if value.tzinfo is not None else value.replace(tzinfo=timezone.utc)


def _remainder_volume(remainder: str) -> int | None:
    """Volume number of a plain volume-token remainder ("3", "cilt 3",
    "3 cilt", "birinci kitap"), else None. A trailing "ana kapak" (the
    regular cover, as opposed to a variant) is the same product."""
    remainder = remainder.removesuffix(" ana kapak")
    token = _REMAINDER_VOLUME_RE.fullmatch(remainder)
    if token is not None:
        return int(token.group(1))
    ordinal = _REMAINDER_ORDINAL_RE.fullmatch(remainder)
    if ordinal is not None:
        return _ORDINAL_WORDS[ordinal.group(1)]
    return None


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
    #: Series ids at least one of this store's results resolved to.
    matched_series: set[int] = field(default_factory=set)


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
        #: Lazily built {publisher_family_key: {publisher ids}} (read-only).
        self._family_index: dict[str, set[int]] | None = None
        self._exclusions: set[tuple[str, str]] | None = None

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

        fetched = self._search_all(scrapers, query)

        for scraper, outcome in zip(scrapers, fetched):
            store_report = StoreImportResult(
                store_code=scraper.store_id, store_name=scraper.store_name
            )
            report.stores.append(store_report)

            try:
                if isinstance(outcome, Exception):
                    raise outcome
                results = outcome
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

            gone = self._remove_gone_listings(scraper)
            if gone:
                store_report.reasons["gone"] = store_report.reasons.get("gone", 0) + gone

            # Phase 1: resolve every result to its (volume, store) target.
            groups: dict[tuple[int, int], list[tuple[int | None, SearchResult]]] = {}
            conflict_publishers: dict[str, int] = {}
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
                    if reason == "publisher_conflict":
                        name = (result.publisher or "").strip()
                        conflict_publishers[name] = conflict_publishers.get(name, 0) + 1
                    continue
                volume, store = target
                store_report.matched_series.add(volume.series_id)
                groups.setdefault((volume.id, store.id), []).append(
                    (to_cents(result.price), result)
                )

            # ISBN-proven products leave the volume a title match once put
            # them on, before any group is written (so that volume's own
            # product can take the freed slot in this same run).
            for (volume_id, store_id), items in groups.items():
                volume = self.session.get(Volume, volume_id)
                store = self.session.get(Store, store_id)
                try:
                    for _, result in items:
                        self._release_misplaced_listings(volume, store, result)
                    self.session.commit()
                except Exception:  # noqa: BLE001 - best effort
                    logger.exception("import: could not release misplaced listings for volume %s", volume_id)
                    self.session.rollback()

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
            if conflict_publishers:
                top = sorted(conflict_publishers.items(), key=lambda kv: -kv[1])[:5]
                logger.info("import publisher conflicts: store=%s query=%r publishers=%s",
                            store_report.store_code, query, top)
        report.finished_at = utcnow()
        return report

    @staticmethod
    def _search_all(scrapers: list[BaseScraper], query: str) -> list[list[SearchResult] | Exception]:
        """Search every store for ``query``; results (or the raised error)
        in scraper order.

        The stores are different hosts, so they are searched at the same
        time: each scraper still keeps its own request interval, and an
        import takes as long as its slowest store instead of all of them
        added up. Scrapers never touch the database; everything after this
        stays on the caller's thread and session.
        """
        def search(scraper: BaseScraper) -> list[SearchResult] | Exception:
            scraper.gone_urls = set()
            try:
                with scraper:
                    return scraper.search(query)
            except Exception as exc:  # noqa: BLE001 - isolation by design
                return exc

        if len(scrapers) < 2 or not get_settings().import_parallel_stores:
            return [search(scraper) for scraper in scrapers]
        with ThreadPoolExecutor(max_workers=len(scrapers), thread_name_prefix="yomiba-store") as pool:
            return list(pool.map(search, scrapers))

    def _remove_gone_listings(self, scraper: BaseScraper) -> int:
        """Delete listings of products the store removed (``gone_urls``):
        their link is dead and their price years old."""
        urls = set(getattr(scraper, "gone_urls", None) or ())
        if not urls:
            return 0
        store = self.session.scalar(select(Store).where(Store.code == scraper.store_id))
        if store is None:
            return 0
        listings = self.session.scalars(
            select(StoreListing).where(StoreListing.store_id == store.id, StoreListing.product_url.in_(urls))
        ).all()
        for listing in listings:
            logger.info("import: %s removed %s; deleting listing %s", scraper.store_id, listing.product_url, listing.id)
            self.session.delete(listing)
        self.session.commit()
        return len(listings)

    def verify_unseen_listings(
        self, scraper: BaseScraper, series_ids: set[int], since: datetime
    ) -> int:
        """Re-check listings of ``series_ids`` at ``scraper``'s store that the
        search did not return (``last_checked`` older than ``since``, the
        start of this import) on their own product page.

        For stores that hide sold-out products from search: without this
        the listing kept its last "in stock" until the 48 h stale window.
        Unknown answers leave the listing alone (the stale window still
        applies). Bounded by ``max_detail_requests``. Returns the number of
        listings updated; the caller's session is committed per listing.
        """
        if not getattr(scraper, "verifies_unseen_listings", False) or not series_ids:
            return 0
        store = self.session.scalar(select(Store).where(Store.code == scraper.store_id))
        if store is None:
            return 0
        since = _aware(since)
        rows = self.session.execute(
            select(StoreListing, Volume)
            .join(Volume, Volume.id == StoreListing.volume_id)
            .where(StoreListing.store_id == store.id, Volume.series_id.in_(series_ids))
            .order_by(StoreListing.id)
        ).all()
        unseen = [(l, v) for l, v in rows if l.last_checked is None or _aware(l.last_checked) < since]
        updated = 0
        for listing, volume in unseen[: max(0, get_settings().max_detail_requests)]:
            try:
                check = scraper.check_listing(listing.product_url)
            except Exception:  # noqa: BLE001 - one page must not stop the rest
                logger.warning("import: stock re-check failed for %s", listing.product_url)
                continue
            if check is None:
                continue
            result = SearchResult(
                store_id=scraper.store_id,
                store_name=scraper.store_name,
                title=f"{volume.series.title} {volume.volume_number}",
                product_url=listing.product_url,
                price=check.price,
                in_stock=check.in_stock,
            )
            try:
                self._upsert_listing(volume, store, result)
                self.session.commit()
            except Exception:  # noqa: BLE001 - per-listing isolation
                logger.exception("import: could not store re-check of %s", listing.product_url)
                self.session.rollback()
                continue
            updated += 1
            logger.info(
                "import: %s listing %s not in search; product page says in_stock=%s",
                scraper.store_id, listing.id, check.in_stock,
            )
        return updated

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
        # An admin removed this product from a volume: never attach it again,
        # not even through its ISBN (a store's wrong metadata is the usual cause).
        if (result.store_id, result.product_url) in self._excluded_products():
            return self._reject("excluded")
        # The catalog lists Turkish editions only: an English (978-0/978-1),
        # Japanese, ... ISBN or a non-Turkish language tag is another
        # edition — e.g. VIZ's "Naruto 11" must never become Naruto Cilt 11.
        if is_foreign_isbn(result.isbn) or is_foreign_language(result.language):
            return self._reject("foreign_edition")
        # Neither an ISBN nor a publisher to tell the edition (Kitapseç gives
        # no publisher but appends it to the title: "... VIZ Media"): a
        # foreign manga publisher or English volume wording ("Naruto, Vol.
        # 11") in the title marks another edition. With an ISBN or a named
        # publisher the regular identity rules decide (ISBN wins).
        if not book_isbn(result.isbn) and not (result.publisher or "").strip():
            if _FOREIGN_PUBLISHER_RE.search(title) or _ENGLISH_VOLUME_RE.search(title):
                return self._reject("foreign_edition")

        if not check_manga_relevance(title=title, publisher=result.publisher, isbn=result.isbn,
                                     category=result.category).accept:
            return self._reject("non_book_product")

        # The ISBN of a catalog volume is proof that beats title wording: a
        # binding variant's own book ("Soichi (Bez Cilt)", a deluxe or
        # hardcover edition the catalog lists) carries edition words.
        proven = self._isbn_catalog_volume(book_isbn(result.isbn))
        if proven is not None:
            store = self._resolve_store(result.store_id, result.store_name)
            named = self._edition_named_in_title(proven, title)
            if named.id != proven.id:
                # The shared ISBN once put this product on the holder.
                for listing in self.session.scalars(
                    select(StoreListing).where(
                        StoreListing.store_id == store.id,
                        StoreListing.product_url == result.product_url,
                        StoreListing.volume_id == proven.id,
                    )
                ):
                    self.session.delete(listing)
                proven = named
            self._backfill_cover(proven, result)
            return (proven, store)

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
        isbn = book_isbn(result.isbn)

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
                series = None
            if series is None:
                # Same publisher spelled with/without a corporate suffix
                # ("Gerekli Şeyler" vs "Gerekli Şeyler Yayıncılık").
                series = self._resolve_series_by_publisher_family(publisher_name, series_key)
        else:
            series = self._resolve_series_no_publisher(series_key)

        if series is None and series_key.endswith(" manga") and parsed.volume_number is not None:
            # A store's generic suffix is only a secondary exact key. Never
            # use prefix/fuzzy matching or drop edition words.
            shorter = series_key.removesuffix(" manga")
            if publisher_name:
                series = self._resolve_series_for_publisher(publisher, shorter) if publisher else None
                if series is None:
                    series = self._resolve_series_by_publisher_family(publisher_name, shorter)
            else:
                series = self._resolve_series_no_publisher(shorter)
        if series is None:
            if self._non_catalog_holder is not None:
                return self._reject("non_catalog_volume")
            if parsed.evidence in {"numeric_metadata", "ambiguous_numbers"}:
                reason = "ambiguous_volume"
            else:
                reason = "publisher_conflict" if publisher_name else "no_series_match"
            edition = self._edition_title_volume(result)
            if edition is not None:
                return (edition, store)
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
        publisher_name = (result.publisher or "").strip()
        remainder_number = None
        how = "prefix"
        # "Dragon Ball 9&10" / "Oldboy Cilt 5-6": a 2-in-1 book the catalog
        # knows by its span. Checked first: the prefix rule below would read
        # the "9 10" remainder as a box set.
        omnibus = self._catalog_series_by_range(result.title, publisher_name)
        match = None if omnibus else self._catalog_series_prefix(title_key, publisher_name)
        if match is not None and match[1]:
            if _REMAINDER_COLLECTION_RE.search(match[1]):
                return self._reject("box_set")
            if _remainder_volume(match[1]) is None:
                # "Ragnarok Valkürleri - Tuhaf Öykü Cilt 3" also prefixes the
                # shorter "Ragnarok Valkürleri"; the rest is not a volume
                # token, so this prefix proves nothing — try the stricter
                # alternatives below.
                match = None
        if omnibus is not None:
            series, remainder_number = omnibus
            how = "omnibus span"
        elif match is None:
            # "Rosario + Vampire - Tılsımlı Kolye ve Vampir 8": the catalog
            # title starts after a dash separator (original title first).
            found = self._catalog_series_after_dash(result.title, publisher_name)
            how = "title after dash"
            if found is None:
                # "Yalnız Kurt ve Yavrusu Cilt 24 - Küçücük Ellerde": catalog
                # title + volume, then a per-volume subtitle.
                found = self._catalog_series_before_dash(result.title, publisher_name)
                how = "title before volume subtitle"
            if found is None:
                # "Kamisama Kiss Cilt 7" for the catalog title "Kamisama Kiss
                # -Tanrılık Görevine Başladım": store omits the subtitle.
                found = self._catalog_series_by_head(result.title, publisher_name)
                how = "title without subtitle"
            if found is None:
                return self._reject(reason)
            series, remainder_number = found
        else:
            series, remainder = match
            if remainder:
                if _REMAINDER_COLLECTION_RE.search(remainder):
                    return self._reject("box_set")
                remainder_number = _remainder_volume(remainder)
                if remainder_number is None:
                    return self._reject(reason)
        store = self._resolve_store(result.store_id, result.store_name)
        isbn = book_isbn(result.isbn)
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
        logger.info("import: %r matched catalog title %r by %s", result.title, series.title, how)
        return (volume, store)

    def _catalog_series_by_range(self, raw_title: str, publisher_name: str):
        """Omnibus book titled by its original-volume span.

        "Dragon Ball 9&10" -> the catalog volume that covers exactly 9-10
        (Mangakol "Cilt 5", TwoInOne). The title before the span must be
        exactly one catalog title (publisher-family filtered). Only volumes
        the catalog marks with that span qualify, so a real "1-2" box of a
        single-volume edition never maps onto volume 1.
        """
        span = parse_volume_range(raw_title)
        if span is None:
            return None
        match = self._catalog_series_prefix(normalize_text(span.base_title), publisher_name)
        if match is None or match[1]:
            return None
        series = match[0]
        volume = self.session.scalar(
            select(Volume).where(
                Volume.series_id == series.id,
                Volume.covers_from == span.first,
                Volume.covers_to == span.last,
            )
        )
        if volume is None:
            return None
        return series, volume.volume_number

    def _catalog_series_after_dash(self, raw_title: str, publisher_name: str):
        """Try each part of ``raw_title`` that follows a spaced dash
        (" - ", " -", "- ", en/em dash) as a catalog-title prefix.

        Returns ``(series, volume_number)`` only when the part starts with
        exactly one catalog title (publisher-family filtered), its remainder
        is empty or a plain volume token, and any "Cilt N" in the text
        BEFORE the dash agrees with that number. Otherwise None.
        """
        for m in _DASH_SEPARATOR_RE.finditer(raw_title or ""):
            before, after = raw_title[: m.start()], raw_title[m.end():]
            key = normalize_text(after)
            if not key:
                continue
            match = self._catalog_series_prefix(key, publisher_name)
            if match is None:
                continue
            series, remainder = match
            number = None
            if remainder:
                if _REMAINDER_COLLECTION_RE.search(remainder):
                    continue
                number = _remainder_volume(remainder)
                if number is None:
                    continue
            before_numbers = {int(n) for n in _CILT_NUMBER_RE.findall(normalize_text(before))}
            if before_numbers and before_numbers != {number}:
                continue
            return series, number
        return None

    def _catalog_series_before_dash(self, raw_title: str, publisher_name: str):
        """Catalog title + explicit volume token BEFORE a dash, per-volume
        subtitle after it ("Yalnız Kurt ve Yavrusu Cilt 24 - Küçücük
        Ellerde"). The volume token is required, and the subtitle must carry
        no numbers or collection words (ranges / box sets stay rejected).
        """
        for m in _DASH_SEPARATOR_RE.finditer(raw_title or ""):
            before = normalize_text(raw_title[: m.start()])
            after = normalize_text(raw_title[m.end():])
            if not before or not after:
                continue
            if re.search(r"\d", after) or _REMAINDER_COLLECTION_RE.search(after):
                continue
            match = self._catalog_series_prefix(before, publisher_name)
            if match is None or not match[1]:
                continue
            series, remainder = match
            number = _remainder_volume(remainder)
            if number is not None:
                return series, number
        return None

    def _publisher_ids_for(self, publisher_name: str) -> set[int]:
        ids = set(self._publisher_family_ids(publisher_name))
        publisher = self._find_publisher(publisher_name)
        if publisher is not None:
            ids.add(publisher.id)
        return ids

    def _catalog_series_by_head(self, raw_title: str, publisher_name: str):
        """Store title = catalog title minus a subtitle, plus an explicit
        volume number: "Ragnarok Valkürleri - Tuhaf Öykü Cilt 3" for
        "Ragnarok Valkürleri - Tuhaf Öykü - Lü Bu Fengxian", "Zom 100 Cilt 9"
        for "Zom 100: Ölülerin Yapılacaklar Listesi".

        Strict: explicit volume marker required, the head must not itself be
        a catalog title (that would have matched earlier), publisher family
        must match, and exactly one catalog series may qualify.
        """
        if not publisher_name:
            return None
        ids = self._publisher_ids_for(publisher_name)
        if not ids:
            return None
        catalog = select(CatalogSeries.series_id).distinct()
        family = list(self.session.scalars(
            select(Series).where(Series.id.in_(catalog), Series.publisher_id.in_(ids))
        ))
        found = self._head_by_parser(raw_title, family)
        if found is None:
            found = self._head_by_prefix(raw_title, family)
        return found

    @staticmethod
    def _head_by_parser(raw_title: str, family: list[Series]):
        """Head = catalog title before its LAST dash; the store title parses
        to that head plus an unambiguous volume number."""
        parsed = parse_volume_title(raw_title)
        if parsed.volume_number is None or parsed.evidence in {"numeric_metadata", "ambiguous_numbers"}:
            return None
        if parsed.is_collection:
            return None
        base_key = normalize_text(parsed.base_title)
        if not base_key:
            return None
        candidates = []
        for series in family:
            if series.normalized_title == base_key:
                return None  # exact title exists; not a subtitle case
            separators = list(_DASH_SEPARATOR_RE.finditer(series.title or ""))
            if not separators:
                continue
            last = separators[-1]
            head = normalize_text(series.title[: last.start()])
            if head == base_key:
                candidates.append(series)
        if len(candidates) != 1:
            return None
        return candidates[0], parsed.volume_number

    @staticmethod
    def _head_by_prefix(raw_title: str, family: list[Series]):
        """Head = catalog title before any subtitle separator (dash or
        colon); the store title is exactly that head plus a plain volume
        token. Does not use the generic parser, so numbers inside the head
        ("Zom 100 Cilt 9") are not mistaken for ambiguous volumes."""
        title_key = normalize_text(raw_title)
        if not title_key:
            return None
        found: dict[int, tuple[Series, int]] = {}
        for series in family:
            if series.normalized_title and (
                title_key == series.normalized_title
                or title_key.startswith(series.normalized_title + " ")
            ):
                return None  # the full catalog title is present; not this case
            for sep in _SUBTITLE_SEPARATOR_RE.finditer(series.title or ""):
                head = normalize_text(series.title[: sep.start()])
                if not head or not title_key.startswith(head + " "):
                    continue
                remainder = title_key[len(head):].strip()
                if _REMAINDER_COLLECTION_RE.search(remainder):
                    continue
                number = _remainder_volume(remainder)
                if number is not None:
                    found[series.id] = (series, number)
        if len(found) != 1:
            return None
        return next(iter(found.values()))

    def _catalog_series_prefix(self, title_key: str, publisher_name: str):
        """Longest catalog series title that prefixes ``title_key`` at a word
        boundary; returns ``(series, remainder)`` or None."""
        if not title_key:
            return None
        publisher_ids: set[int] | None = None
        if publisher_name:
            publisher = self._find_publisher(publisher_name)
            publisher_ids = set(self._publisher_family_ids(publisher_name))
            if publisher is not None:
                publisher_ids.add(publisher.id)
            if not publisher_ids:
                return None
        query = select(Series).where(
            Series.id.in_(select(CatalogSeries.series_id).distinct()),
            Series.normalized_title.isnot(None),
        )
        if publisher_ids is not None:
            query = query.where(Series.publisher_id.in_(publisher_ids))
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

    def _excluded_products(self) -> set[tuple[str, str]]:
        """(store code, product URL) pairs admins removed; loaded once per
        service instance (one import run)."""
        if self._exclusions is None:
            self._exclusions = {
                (code, url) for code, url in self.session.execute(
                    select(Store.code, ListingExclusion.product_url)
                    .join(Store, Store.id == ListingExclusion.store_id)
                )
            }
        return self._exclusions

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

    def _publisher_family_ids(self, raw_name: str | None) -> set[int]:
        """Ids of existing publishers in the same family as ``raw_name``
        (see ``publisher_family_key``). Read-only; empty when unknown."""
        key = publisher_family_key(raw_name)
        if not key:
            return set()
        if self._family_index is None:
            index: dict[str, set[int]] = {}
            for pid, name in self.session.execute(select(Publisher.id, Publisher.name)):
                fkey = publisher_family_key(name)
                if fkey:
                    index.setdefault(fkey, set()).add(pid)
            self._family_index = index
        return set(self._family_index.get(key, ()))

    def _resolve_series_by_publisher_family(
        self, publisher_name: str, series_key: str
    ) -> Series | None:
        """Secondary edition check for publisher spelling variants.

        The store's publisher did not resolve (or resolved to a publisher
        without this title). Accept a catalog series only when its normalized
        title equals ``series_key`` exactly (or via the strict bilingual
        bridge) AND its publisher is in the same family as the store's
        publisher, AND exactly one such series exists. Never guesses
        between editions and never creates rows.
        """
        ids = self._publisher_family_ids(publisher_name)
        if not ids or not series_key:
            return None
        candidates = self.session.scalars(
            select(Series).where(
                Series.publisher_id.in_(ids),
                Series.normalized_title == series_key,
                Series.id.in_(select(CatalogSeries.series_id).distinct()),
            )
        ).all()
        if not candidates:
            bridged = {
                s.id: s
                for pid in ids
                if (s := self._find_series_by_bilingual_key(series_key, publisher_id=pid)) is not None
            }
            candidates = list(bridged.values())
        if len(candidates) != 1:
            return None
        series = candidates[0]
        logger.debug(
            "import: publisher %r matched catalog publisher of %r by family key",
            publisher_name, series.title,
        )
        return series

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
    def _isbn_catalog_volume(self, isbn: str | None) -> Volume | None:
        """The numbered catalog volume holding ``isbn``, if any."""
        if not isbn:
            return None
        volume = self.session.scalar(select(Volume).where(Volume.isbn == isbn))
        if volume is None or volume.volume_number < 0 or not self._series_is_catalog(volume.series_id):
            return None
        return volume

    _EDITION_LABEL_RE = re.compile(r"\(([^()]+)\)\s*$")
    #: Label words that do not tell editions apart ("Limitli Baskı" and a
    #: store's "Limitli Sert Kapak" are the same edition).
    _EDITION_GENERIC_WORDS = frozenset({"baski", "kapak", "cilt", "ozel", "edisyon"})
    #: What may follow the series name in an edition product's title:
    #: "[Webtoon|Manga] [Cilt] 3 ...".
    _EDITION_REMAINDER_RE = re.compile(r"^(?:webtoon |manga )?(?:cilt )?0*(\d{1,3})(?: |$)")

    def _edition_words(self, series: Series) -> frozenset[str]:
        """Distinctive words of a variant's label: "Solo Leveling (Varyant
        Kapak)" -> {"varyant"}; empty for a main edition."""
        match = self._EDITION_LABEL_RE.search(series.title)
        if match is None:
            return frozenset()
        return frozenset(normalize_text(match.group(1)).split()) - self._EDITION_GENERIC_WORDS

    def _edition_named_in_title(self, proven: Volume, title: str) -> Volume:
        """The volume a product belongs to when its title names ANOTHER
        edition than the one holding its ISBN.

        * A publisher may print two editions under one ISBN (Solo Leveling 5
          "Varyant Kapak" and "Limitli Sert Kapak"); the ISBN is unique here,
          so one of them holds it. A title naming the sibling edition, whose
          volume has no ISBN of its own, goes to that sibling.
        * A store may put a variant's ISBN on the regular book ("... Cilt 2
          (2. Hamur – Ana Kapak)" carrying the limited edition's ISBN): "Ana
          Kapak" names the main edition.

        Otherwise ``proven``.
        """
        from .catalog_service import other_editions

        key = normalize_text(title)
        words = set(key.split())
        own = self._edition_words(proven.series)
        if own and own <= words:
            return proven

        def twin_in(series: Series) -> Volume | None:
            return self.session.scalar(
                select(Volume).where(
                    Volume.series_id == series.id,
                    Volume.volume_number == proven.volume_number,
                )
            )

        for sibling in other_editions(self.session, proven.series_id):
            named = self._edition_words(sibling)
            if not named:
                if own and "ana kapak" in key:
                    twin = twin_in(sibling)
                    if twin is not None:
                        return twin
                continue
            if named <= words:
                twin = twin_in(sibling)
                if twin is not None and twin.isbn is None:
                    return twin
        return proven

    def _edition_title_volume(self, result: SearchResult) -> Volume | None:
        """A variant edition's volume for a product no ISBN could place.

        Some variant books carry no real ISBN (Solo Leveling 1 "Varyant
        Kapak" has a store barcode, the "Limitli Sert Kapak" volumes none),
        and stores add words the plain title match cannot read ("Solo
        Leveling Webtoon Cilt 1 (Kuşe Kağıt – Varyant Kapak)"). The title
        must start with the variant's base title, continue with the volume
        ("[Webtoon|Manga] [Cilt] N") and contain the variant's distinctive
        label words; exactly one catalog variant may fit.
        """
        key = normalize_text(result.title)
        words = set(key.split())
        publisher_name = (result.publisher or "").strip()
        publisher_ids: set[int] | None = None
        if publisher_name:
            publisher = self._find_publisher(publisher_name)
            publisher_ids = set(self._publisher_family_ids(publisher_name))
            if publisher is not None:
                publisher_ids.add(publisher.id)
            if not publisher_ids:
                return None
        found: list[tuple[Series, int]] = []
        variants = self.session.scalars(
            select(Series)
            .join(CatalogSeries, CatalogSeries.series_id == Series.id)
            .where(CatalogSeries.mangakol_slug.contains("~", autoescape=True))
            .distinct()
        )
        for series in variants:
            named = self._edition_words(series)
            if not named or not named <= words:
                continue
            if publisher_ids is not None and series.publisher_id not in publisher_ids:
                continue
            base = normalize_text(self._EDITION_LABEL_RE.sub("", series.title))
            if not base or not key.startswith(base + " "):
                continue
            remainder = key[len(base) + 1:]
            match = self._EDITION_REMAINDER_RE.match(remainder)
            numbers = list(self.session.scalars(
                select(Volume.volume_number).where(
                    Volume.series_id == series.id, Volume.volume_number >= 0
                )
            ))
            if match is not None and int(match.group(1)) in numbers:
                found.append((series, int(match.group(1))))
            elif len(numbers) == 1 and not remainder.startswith("cilt "):
                # A single-book edition needs no volume number: "Afro
                # Samuray (444 Adet Limitli Sert Kapak)" is not volume 444.
                found.append((series, numbers[0]))
        if len(found) != 1:
            return None
        series, number = found[0]
        return self._resolve_volume(series, book_isbn(result.isbn), number, result, title_verified=True)

    def _release_misplaced_listings(self, volume: Volume, store: Store, result: SearchResult) -> None:
        """Drop this product's listing from ANOTHER volume when the ISBN
        proves it belongs to ``volume``: stores often title both bindings
        plainly "Soichi", so before the catalog knew the Bez Cilt edition a
        title match put its price on the regular volume."""
        isbn = book_isbn(result.isbn)
        if not isbn or volume.isbn != isbn:
            return
        for listing in self.session.scalars(
            select(StoreListing).where(
                StoreListing.store_id == store.id,
                StoreListing.product_url == result.product_url,
                StoreListing.volume_id != volume.id,
            )
        ):
            logger.info(
                "import: ISBN %s proves %s belongs to volume %s; removing its listing %s from volume %s",
                isbn, result.product_url, volume.id, listing.id, listing.volume_id,
            )
            self.session.delete(listing)
        self.session.flush()

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
