"""Mangakol catalog discovery and safe metadata/visibility updates.

During P0, discovery may add series and volumes with NULL ISBNs. ISBN
candidates are reported only: no fills, clears, transfers or identity
merges. Publisher aliases and existing cilt/listing/history IDs survive.
This bounded metadata pass is not the future full independent ISBN audit.
"""

from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, select
from sqlalchemy.exc import OperationalError
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    CatalogSeries,
    Publisher,
    PublisherAlias,
    Series,
    Volume,
)
from ..normalization import ORIGINAL_TITLE_SEPARATOR, normalize_publisher, normalize_text
from ..normalization.isbn import book_isbn
from ..normalization.text import slugify
from ..scrapers.mangakol import (
    CatalogManga,
    CatalogVolumeDetails,
    MangakolCatalogScraper,
)
from ..utils import utcnow
from .covers import PROVISIONAL_GIVE_UP, is_mangakol_url, volume_is_out

#: Attempts per catalog entry when SQLite reports "database is locked".
#: The merge reads first and writes later in one transaction; in WAL mode a
#: commit by another connection in between (page-view analytics, cover
#: worker) fails the first write at once, without the busy timeout. A fresh
#: transaction then succeeds (Wotakoi, Noragami, Ningen Shikkaku,
#: 2026-10-21).
_LOCKED_ATTEMPTS = 3


def _is_locked(exc: Exception) -> bool:
    return isinstance(exc, OperationalError) and "database is locked" in str(exc)


logger = logging.getLogger("yomiba.catalog")

#: Manifest slug of a binding variant: "<slug>~clothbound".
VARIANT_SEP = "~"

#: Fallback publisher for mangas without a "Yerel Yayıncı" value.
_UNKNOWN_PUBLISHER = "Bilinmiyor"
#: Minimum normalized-name length for prefix/containment publisher matching.
_PUB_MIN_MATCH_LEN = 3
_PUB_SUFFIX_RE = re.compile(r"^(.*)\s*\(([^()]+)\)$")


@dataclass
class CatalogSyncReport:
    """Outcome summary of one catalog sync run."""

    started_at: datetime = field(default_factory=utcnow)
    manga_total: int = 0
    manga_scanned: int = 0
    manga_failed: int = 0
    #: Kept for report compatibility; exclusions no longer affect membership.
    manga_skipped_excluded: int = 0
    series_created: int = 0
    series_merged: int = 0
    volumes_added: int = 0
    isbn_candidates: list[dict] = field(default_factory=list)
    volumes_retired: int = 0
    release_status_updated: int = 0
    announced_volumes: int = 0
    covers_backfilled: int = 0
    #: Volumes whose Mangakol image changed (e.g. the Japanese placeholder
    #: swapped for the Turkish cover); recent ones are queued for a new cover.
    covers_changed: int = 0
    #: Legacy merge counters are retained for API compatibility; P0 leaves them zero.
    publishers_merged: int = 0
    #: Series absorbed into a same-title series under the merged publisher.
    series_absorbed: int = 0
    #: Volumes folded into an existing volume of the merged series.
    volumes_merged: int = 0
    #: Volume pages opened for ISBNs / ISBNs stored / ISBNs already held by
    #: another volume (never moved; see ``isbn_conflict_details``).
    isbn_pages: int = 0
    isbns_added: int = 0
    isbns_deferred: int = 0
    isbn_conflicts: int = 0
    isbn_conflict_details: list[str] = field(default_factory=list)
    #: Legacy store-created copies (volume -1) folded into the catalog volume
    #: that already carries every one of their store products.
    isbn_phantoms_merged: int = 0
    errors: list[str] = field(default_factory=list)

    @property
    def ok(self) -> bool:
        return self.manga_failed == 0 and not self.errors


class CatalogSyncService:
    """Upserts mangakol's catalog (series + volumes) into the local DB."""

    def __init__(
        self,
        session: Session,
        *,
        scraper: MangakolCatalogScraper | None = None,
    ) -> None:
        self.session = session
        self.scraper = scraper or MangakolCatalogScraper()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def sync(self) -> CatalogSyncReport:
        report = CatalogSyncReport()
        self._isbn_budget = max(0, get_settings().mangakol_max_isbn_requests)
        #: volume id -> its catalog page, for every volume seen this sync.
        self._volume_urls: dict[int, str] = {}
        try:
            refs = self.scraper.list_manga()
        except Exception:
            self.scraper.close()
            raise
        report.manga_total = len(refs)
        if not getattr(self.scraper, "catalog_list_complete", True):
            report.errors.append("Mangakol catalog list is incomplete")
        if not refs:
            report.errors.append("mangakol catalog list returned no manga")
            self.scraper.close()
            return report

        try:
            self._consolidate_publisher_aliases(report)
            self.session.commit()
        except Exception:
            self.session.rollback()
            self.scraper.close()
            raise

        variant_slugs: set[str] = set()
        fetched_slugs: set[str] = set()
        try:
            for ref in refs:
                report.manga_scanned += 1
                try:
                    fetched = self.scraper.fetch_manga(ref.slug)
                except Exception as exc:  # noqa: BLE001 - isolation by design
                    logger.exception(
                        "catalog sync: failed to fetch /manga/%s", ref.slug
                    )
                    report.manga_failed += 1
                    report.errors.append(f"{ref.slug}: {type(exc).__name__}: {exc}")
                    continue
                fetched_slugs.add(ref.slug)
                if not fetched.volumes_complete:
                    report.errors.append(f"{ref.slug}: incomplete volume snapshot")
                entries = [fetched, *self._variant_entries(fetched)]
                variant_slugs.update(e.slug for e in entries[1:])
                for manga in entries:
                    self._sync_entry(manga, report)
        finally:
            self.scraper.close()
        self._resolve_isbns(report)
        self._merge_redundant_phantoms(report)
        # A successful sync must represent exactly the live snapshot. Stale
        # slug identity changes require reconciliation; do not delete a
        # Series or guess an edition match during an ordinary sync.
        manifest_slugs = list(self.session.scalars(select(CatalogSeries.mangakol_slug)))
        live_slugs = {ref.slug for ref in refs} | variant_slugs
        missing = live_slugs - set(manifest_slugs)
        # A variant of a manga whose page failed this run is not stale.
        stale = {
            slug for slug in set(manifest_slugs) - live_slugs
            if VARIANT_SEP not in slug or slug.split(VARIANT_SEP)[0] in fetched_slugs
        }
        if missing:
            report.errors.append(f"live slugs missing from manifest: {sorted(missing)}")
        if stale:
            report.errors.append(f"stale manifest slugs require reconciliation: {sorted(stale)}")
        if len(manifest_slugs) != len(set(manifest_slugs)):
            report.errors.append("duplicate Mangakol slugs in catalog manifest")
        return report

    def _variant_entries(self, manga: CatalogManga) -> list[CatalogManga]:
        """Each extra binding ("Bez Cilt") as its own catalog entry: a
        separate series "Soichi (Bez Cilt)" under the same publisher, with
        the manifest slug "<slug>~clothbound". Its books have their own
        ISBNs, so store listings reach them ISBN-first. No original title:
        that key bridges foreign-titled store products to the main series."""
        base = self._clean_title(manga.title, manga.local_publisher) or manga.title.strip()
        return [
            CatalogManga(
                slug=f"{manga.slug}{VARIANT_SEP}{variant.format.lower()}",
                title=f"{base} ({variant.label})",
                local_publisher=manga.local_publisher,
                volumes=variant.volumes,
                author=manga.author,
                illustrator=manga.illustrator,
                jp_status=manga.jp_status,
                tr_status=manga.tr_status,
                volumes_complete=manga.volumes_complete,
            )
            for variant in getattr(manga, "variants", ()) or ()
            if variant.volumes
        ]

    def _sync_entry(self, manga: CatalogManga, report: CatalogSyncReport) -> None:
        """Merge one catalog entry and backfill its ISBNs (isolated)."""
        counts_before = (
            report.series_created, report.series_merged,
            report.volumes_added, report.covers_backfilled, report.covers_changed,
            report.volumes_retired, report.release_status_updated, report.announced_volumes,
        )
        try:
            series = self._merge_with_retry(manga, report, counts_before)
        except Exception as exc:  # noqa: BLE001 - isolation by design
            (
                report.series_created, report.series_merged,
                report.volumes_added, report.covers_backfilled, report.covers_changed,
                report.volumes_retired, report.release_status_updated, report.announced_volumes,
            ) = counts_before
            logger.exception(
                "catalog sync: failed to merge /manga/%s", manga.slug
            )
            report.manga_failed += 1
            report.errors.append(
                f"{manga.slug}: {type(exc).__name__}: {exc}"
            )
            return
        self.session.commit()
        if series is not None:
            try:
                self._backfill_isbns(series, manga, report)
            except Exception:  # noqa: BLE001 - ISBNs are best effort
                logger.exception("catalog sync: ISBN backfill failed for /manga/%s", manga.slug)
                self.session.rollback()

    def _merge_with_retry(self, manga: CatalogManga, report: CatalogSyncReport, counts_before):
        """``_merge_manga`` in a savepoint, retried on "database is locked"
        (see ``_LOCKED_ATTEMPTS``) in a fresh transaction."""
        for attempt in range(1, _LOCKED_ATTEMPTS + 1):
            try:
                with self.session.begin_nested():
                    return self._merge_manga(manga, report)
            except OperationalError as exc:
                if attempt == _LOCKED_ATTEMPTS or not _is_locked(exc):
                    raise
                (
                    report.series_created, report.series_merged,
                    report.volumes_added, report.covers_backfilled, report.covers_changed,
                    report.volumes_retired, report.release_status_updated, report.announced_volumes,
                ) = counts_before
                self.session.rollback()
                logger.warning("catalog sync: database locked for /manga/%s; retry %d",
                               manga.slug, attempt)
                time.sleep(attempt)

    # ------------------------------------------------------------------
    # Merge logic
    # ------------------------------------------------------------------
    def _merge_manga(self, manga: CatalogManga, report: CatalogSyncReport) -> None:
        cleaned_title = self._clean_title(manga.title, manga.local_publisher)
        if not cleaned_title:
            cleaned_title = manga.title.strip()
        if not cleaned_title:
            logger.warning("catalog sync: %s has no usable title; skipped", manga.slug)
            return

        # Slug-first identity: a mangakol slug is the canonical identity of
        # one manga. If it is already in the manifest (under any publisher
        # or title variant), merge into THAT series — a twin series can then
        # never be opened, whatever the store imports called the edition.
        series = None
        row = self.session.scalar(
            select(CatalogSeries).where(CatalogSeries.mangakol_slug == manga.slug)
        )
        if row is not None:
            series = self.session.get(Series, row.series_id)
            if series is None:
                self.session.delete(row)  # dangling manifest row
            else:
                report.series_merged += 1
        if series is None:
            publisher = self._resolve_publisher(manga.local_publisher)
            series_key = normalize_text(cleaned_title)
            series = self._resolve_series(publisher, series_key)
            if series is None:
                series = self._create_series(publisher, cleaned_title, series_key)
                report.series_created += 1
                logger.info(
                    "catalog sync: created series %r (publisher %r) from mangakol %s",
                    cleaned_title, publisher.name, manga.slug,
                )
            else:
                report.series_merged += 1

        self._mark_catalog_series(series, manga.slug)

        # Keep the original-title key fresh from the catalog source. Only a
        # non-empty value overwrites: a page without an h2 never erases an
        # earlier original title.
        if manga.original_title:
            key = self._original_title_key(manga.original_title)
            if key and series.original_title != key:
                series.original_title = key
        # Credits and status follow the catalog source (a page without
        # them never erases).
        for attr in ("author", "illustrator", "jp_status", "tr_status"):
            value = (getattr(manga, attr, None) or "").strip()[:200]
            if value and getattr(series, attr) != value:
                setattr(series, attr, value)

        incoming_numbers = {v.number if v.number is not None else -1 for v in manga.volumes}
        # Only a complete, non-empty source snapshot can retire legacy
        # extra volumes. Keep rows, prices and user references intact.
        aliases = self.session.scalars(select(CatalogSeries).where(
            CatalogSeries.series_id == series.id
        )).all()
        if manga.volumes_complete and incoming_numbers and len(aliases) <= 1:
            for old in self.session.scalars(select(Volume).where(Volume.series_id == series.id)):
                if old.volume_number not in incoming_numbers:
                    if old.catalog_present is not False:
                        report.volumes_retired += 1
                    old.catalog_present = False
                    old.catalog_released = False
        for volume in manga.volumes:
            number = volume.number if volume.number is not None else -1
            existing = self.session.scalar(
                select(Volume).where(
                    Volume.series_id == series.id,
                    Volume.volume_number == number,
                )
            )
            covers = getattr(volume, "covers", None)
            if not volume.released:
                report.announced_volumes += 1
            if existing is not None:
                if existing.catalog_released != volume.released:
                    report.release_status_updated += 1
                    if volume.released and (not existing.isbn or existing.page_count is None or existing.release_date is None):
                        existing.details_checked_at = None
                existing.catalog_present = True
                existing.catalog_released = volume.released
                if existing.cover_url is None and volume.cover_url:
                    existing.cover_url = volume.cover_url
                    report.covers_backfilled += 1
                elif (volume.cover_url and existing.cover_url != volume.cover_url
                      and is_mangakol_url(existing.cover_url)):
                    self._catalog_cover_changed(existing, volume.cover_url)
                    report.covers_changed += 1
                # The omnibus span follows the catalog source (only a known
                # span overwrites; a page without one never erases it).
                if covers and (existing.covers_from, existing.covers_to) != covers:
                    existing.covers_from, existing.covers_to = covers
                continue
            self.session.add(
                Volume(
                    series_id=series.id,
                    volume_number=number,
                    catalog_released=volume.released,
                    catalog_present=True,
                    cover_url=volume.cover_url,
                    covers_from=covers[0] if covers else None,
                    covers_to=covers[1] if covers else None,
                )
            )
            report.volumes_added += 1
        return series

    @staticmethod
    def _catalog_cover_changed(volume: Volume, url: str) -> None:
        """Mangakol shows a new image for the volume. A stored Mangakol cover
        of a volume that came out lately is queued to be replaced (services/covers.py, provisional covers); older volumes keep
        theirs, so a Mangakol CDN move does not re-download the catalog."""
        volume.cover_url = url
        if volume.cover_key is None or volume.cover_source != "mangakol":
            return
        if not volume_is_out(volume):
            # A new pre-release image is no Turkish cover either: it must
            # not count as the replacement once the volume is out.
            if volume.cover_provisional:
                volume.cover_origin_url = url
            return
        recent = utcnow().date() - PROVISIONAL_GIVE_UP
        if volume.release_date is None or volume.release_date >= recent:
            volume.cover_provisional = True
            volume.cover_checked_at = None

    def _backfill_isbns(self, series: Series, manga: CatalogManga, report: CatalogSyncReport) -> None:
        """Read each released volume's catalog page: page count, local
        release date and the ISBN Mangakol lists, stored as
        ``catalog_isbn``. Whether it becomes the volume's ISBN is the
        resolver's decision (services/isbn_resolver.py), run for every
        catalog volume at the end of the sync."""
        fetch_details = getattr(self.scraper, "fetch_volume_details", None)
        fetch_isbn = getattr(self.scraper, "fetch_volume_isbn", None)
        if fetch_details is None and fetch_isbn is None:
            return
        recheck = utcnow() - timedelta(days=7)
        for cv in manga.volumes:
            if self._isbn_budget <= 0:
                return
            if cv.number is None or not cv.url or not cv.released:
                continue
            volume = self.session.scalar(select(Volume).where(
                Volume.series_id == series.id, Volume.volume_number == cv.number))
            if volume is None or volume.catalog_present is False:
                continue
            checked = volume.details_checked_at
            if checked is not None and checked.tzinfo is None:
                checked = checked.replace(tzinfo=timezone.utc)
            if checked is not None and checked > recheck:
                continue
            self._isbn_budget -= 1
            report.isbn_pages += 1
            try:
                details = (fetch_details(cv.url) if fetch_details else
                           CatalogVolumeDetails(isbn=fetch_isbn(cv.url)))
            except Exception:
                logger.warning("catalog metadata unavailable: %s", cv.url)
                continue
            if details is None:
                continue
            volume.details_checked_at = utcnow()
            source_isbn = book_isbn(details.isbn)
            if source_isbn and volume.catalog_isbn != source_isbn:
                volume.catalog_isbn = source_isbn
            holder = self.session.scalar(select(Volume).where(Volume.isbn == source_isbn)) if source_isbn else None
            if holder is not None and holder.id != volume.id and holder.volume_number != volume.volume_number:
                # The page carries another numbered book's ISBN, so its page
                # count / date may be that book's too: keep ours empty.
                self.session.commit()
                continue
            if details.page_count and volume.page_count is None:
                volume.page_count = details.page_count
            if details.release_date and volume.release_date is None:
                volume.release_date = details.release_date
            self.session.commit()

    def _merge_redundant_phantoms(self, report: CatalogSyncReport) -> None:
        """Fold a legacy phantom (Yıldızların Sesi #2439) into the one catalog
        volume of its series that already lists every one of its store
        products — the same product page is the same book. Its price history
        joins that volume's. Never when users point at the phantom, or when
        its ISBN is another book's (Komünist Manifesto #2451: the Kırmızı Kedi
        edition, sharing a product only through a wrong match)."""
        from ..models import StoreListing
        from .catalog_service import legacy_phantom_condition
        from .phantom_review import has_personal_rows, merge_volume_rows

        catalog_series = select(CatalogSeries.series_id).distinct()
        phantoms = list(self.session.scalars(select(Volume).where(
            Volume.series_id.in_(catalog_series), legacy_phantom_condition())))
        for phantom in phantoms:
            products = set(self.session.execute(select(StoreListing.store_id, StoreListing.product_url)
                                                .where(StoreListing.volume_id == phantom.id)).all())
            if not products or has_personal_rows(self.session, phantom.id):
                continue
            holders: dict[int, set] = {}
            for vid, store_id, url in self.session.execute(
                    select(StoreListing.volume_id, StoreListing.store_id, StoreListing.product_url)
                    .join(Volume, Volume.id == StoreListing.volume_id)
                    .where(Volume.series_id == phantom.series_id, Volume.volume_number >= 0)):
                holders.setdefault(vid, set()).add((store_id, url))
            targets = [vid for vid, held in holders.items() if products <= held]
            if len(targets) != 1:
                continue
            target = self.session.get(Volume, targets[0])
            if phantom.isbn and phantom.isbn != target.isbn:
                continue
            try:
                merge_volume_rows(self.session, phantom.id, target.id)
                self.session.commit()
            except Exception:
                self.session.rollback()
                logger.exception("catalog sync: merging phantom %s into %s failed", phantom.id, target.id)
                continue
            logger.info("catalog sync: legacy phantom %s merged into volume %s", phantom.id, target.id)
            report.isbn_phantoms_merged += 1

    def _resolve_isbns(self, report: CatalogSyncReport) -> None:
        """Run the ISBN resolver over every catalog volume (cheap, local)."""
        from ..models import IsbnIssue
        from .isbn_resolver import resolve_many

        ids = list(self.session.scalars(
            select(Volume.id).where(
                Volume.series_id.in_(select(CatalogSeries.series_id).distinct()),
                Volume.volume_number >= 0,
                Volume.catalog_present.is_not(False),
            ).order_by(Volume.id)
        ))
        try:
            counts = resolve_many(self.session, ids)
            self.session.commit()
        except Exception:
            self.session.rollback()
            logger.exception("catalog sync: ISBN resolution failed")
            report.errors.append("ISBN resolution failed")
            return
        report.isbns_added = counts.get("catalog", 0) + counts.get("stores", 0)
        report.isbn_conflicts = self.session.scalar(select(func.count()).select_from(IsbnIssue)) or 0
        report.isbn_conflict_details = [
            f"volume {row.volume_id}: {row.kind}"
            for row in self.session.scalars(select(IsbnIssue).order_by(IsbnIssue.volume_id).limit(50))
        ]

    def _page_isbn(self, url: str | None) -> str | None:
        """ISBN a catalog volume page lists (None when unknown/unreadable)."""
        if not url:
            return None
        fetch_details = getattr(self.scraper, "fetch_volume_details", None)
        fetch_isbn = getattr(self.scraper, "fetch_volume_isbn", None)
        try:
            if fetch_details is not None:
                details = fetch_details(url)
                return details.isbn if details is not None else None
            return fetch_isbn(url) if fetch_isbn is not None else None
        except Exception:  # noqa: BLE001 - unknown is a valid answer
            logger.warning("catalog sync: volume page failed for %s", url)
            return None

    def _variant_series_ids(self, slug: str) -> set[int]:
        """Series of the variants of a base manga ("soichi" -> the series of
        "soichi~clothbound", ...)."""
        return set(self.session.scalars(
            select(CatalogSeries.series_id)
            .where(CatalogSeries.mangakol_slug.startswith(f"{slug}{VARIANT_SEP}", autoescape=True))
        ))

    def _base_series_id(self, slug: str) -> int | None:
        """Series of a variant's base manga ("soichi~clothbound" -> the
        "soichi" series); None for a slug that is not a variant."""
        if VARIANT_SEP not in slug:
            return None
        return self.session.scalar(
            select(CatalogSeries.series_id)
            .where(CatalogSeries.mangakol_slug == slug.split(VARIANT_SEP)[0])
        )

    @staticmethod
    def _original_title_key(raw: str) -> str:
        """Normalized search key for a detail page's original-title h2.

        mangakol sometimes lists the same title twice with different
        lettering (``One-Punch Man | One Punch-Man | ワンパンマン``). Each
        ``|`` part is normalized separately, empties (e.g. CJK-only parts
        after diacritic/CJK folding) are dropped, duplicates collapse, and
        distinct parts are joined with ``ORIGINAL_TITLE_SEPARATOR`` so each
        stays usable on its own: a joined "tokyo revengers toukyou revengers"
        was one store query that strict all-words searches (Gerekli Şeyler)
        never answered (Tokyo İntikamcıları, 2026-10-21).
        """
        seen: set[str] = set()
        parts: list[str] = []
        for part in raw.split("|"):
            key = normalize_text(part)
            if key and key not in seen:
                seen.add(key)
                parts.append(key)
        return ORIGINAL_TITLE_SEPARATOR.join(parts)

    @staticmethod
    def _clean_title(title: str, local_publisher: str | None) -> str:
        """Strip a trailing "(Publisher)" suffix that matches the entry's own
        local publisher: "Berserk (Athica)" + "Athica" -> "Berserk".

        The suffix is kept when it does not look like the publisher
        (protects meaningful parentheticals).
        """
        match = _PUB_SUFFIX_RE.match(title.strip())
        if not match or not local_publisher:
            return title.strip()
        base, suffix = match.group(1).strip(), match.group(2).strip()
        if not base:
            return title.strip()
        if _names_related(normalize_text(suffix), normalize_text(local_publisher)):
            return base
        return title.strip()

    def _resolve_series(self, publisher: Publisher, series_key: str) -> Series | None:
        """Find the series to merge into, or None when one must be created.

        See the module docstring (strategy point 3) for the full rule.
        """
        series = self.session.scalar(
            select(Series).where(
                Series.publisher_id == publisher.id,
                Series.normalized_title == series_key,
            )
        )
        if series is not None:
            return series

        candidates = list(
            self.session.scalars(
                select(Series).where(Series.normalized_title == series_key)
            ).all()
        )
        bilinmiyor_id = self._unknown_publisher_id()
        under_unknown = [c for c in candidates if c.publisher_id == bilinmiyor_id]

        if publisher.normalized_name != normalize_publisher(_UNKNOWN_PUBLISHER):
            # Real publisher but no series for it: merge when the only
            # existing edition has an UNKNOWN publisher (single
            # unambiguous candidate, ImportService rule).
            if len(candidates) == 1 and under_unknown:
                return candidates[0]
            return None

        # Source has no publisher: prefer the existing "Bilinmiyor"
        # edition (must not violate the (publisher, title) unique
        # constraint); then the single existing edition of any
        # publisher; otherwise a "Bilinmiyor" edition is created.
        if under_unknown:
            return under_unknown[0]
        if len(candidates) == 1:
            return candidates[0]
        return None

    def _unknown_publisher_id(self) -> int | None:
        publisher = self.session.scalar(
            select(Publisher).where(
                Publisher.normalized_name == normalize_publisher(_UNKNOWN_PUBLISHER)
            )
        )
        return publisher.id if publisher is not None else None

    # ------------------------------------------------------------------
    # Publisher alias consolidation
    # ------------------------------------------------------------------
    def _consolidate_publisher_aliases(self, report: CatalogSyncReport) -> None:
        """Not run. The fuzzy publisher/series merge of the store-import era
        (removed in P0, 2026-10-15) is no longer needed: store imports never
        create publishers or series, and catalog identities come from the
        Mangakol slug. Kept as a hook; ``publishers_merged`` stays 0."""
        return

    def _unique_slug(
        self, publisher_id: int, series_key: str, *, exclude_id: int | None = None
    ) -> str:
        base = slugify(series_key)
        candidate = base
        suffix = 2
        while True:
            query = select(Series.id).where(
                Series.publisher_id == publisher_id,
                Series.slug == candidate,
            )
            if exclude_id is not None:
                query = query.where(Series.id != exclude_id)
            if self.session.scalar(query) is None:
                return candidate
            candidate = f"{base}-{suffix}"
            suffix += 1

    def _resolve_publisher(self, raw_name: str | None) -> Publisher:
        name = (raw_name or "").strip()
        if not name:
            return self._get_publisher(_UNKNOWN_PUBLISHER)

        # 1) exact normalized match (same key as ImportService uses)
        key = normalize_publisher(name)
        candidates = [
            self.session.scalar(
                select(Publisher).where(Publisher.normalized_name == key)
            )
        ]
        # 1b) curated alias (the same table ImportService consults): the DB
        #     may hold a renamed variant row; the alias points at the
        #     canonical one, so a variant name never opens a twin row.
        alias = self.session.scalar(
            select(PublisherAlias).where(PublisherAlias.normalized_alias == key)
        )
        if alias is not None:
            target = self.session.get(Publisher, alias.publisher_id)
            if target is not None:
                candidates.append(target)
        # 2) prefix/containment against existing normalized names:
        #    mangakol uses short forms ("Athica") while the store imports
        #    created the full form ("Athica Yayınleri").
        for publisher in self.session.scalars(select(Publisher)).all():
            if _names_related(publisher.normalized_name, key):
                candidates.append(publisher)

        candidates = [c for c in candidates if c is not None]
        if candidates:
            # Several rows can refer to the same real company ("Athica"
            # vs "Athica Yayınleri"); prefer the most complete (longest
            # normalized) name, tie-broken by id for determinism.
            return max(
                dict.fromkeys(candidates),
                key=lambda p: (len(p.normalized_name), -p.id),
            )
        # 3) create with the scraped name (real data, no guessing)
        publisher = Publisher(name=name, normalized_name=key)
        self.session.add(publisher)
        self.session.flush()
        logger.info("catalog sync: created publisher %r", name)
        return publisher

    def _get_publisher(self, name: str) -> Publisher:
        key = normalize_publisher(name)
        publisher = self.session.scalar(
            select(Publisher).where(Publisher.normalized_name == key)
        )
        if publisher is None:
            publisher = Publisher(name=name, normalized_name=key)
            self.session.add(publisher)
            self.session.flush()
        return publisher

    def _create_series(self, publisher: Publisher, title: str, series_key: str) -> Series:
        series = Series(
            publisher_id=publisher.id,
            title=title,
            normalized_title=series_key,
            slug=self._unique_slug(publisher.id, series_key),
        )
        self.session.add(series)
        self.session.flush()
        return series

    def _mark_catalog_series(self, series: Series, mangakol_slug: str) -> None:
        """Record that ``series`` belongs to the tracked catalog.

        Idempotent: the (series_id, mangakol_slug) pair is the primary
        key, so re-syncing the same entry never duplicates the row.
        """
        existing = self.session.scalar(
            select(CatalogSeries).where(
                CatalogSeries.series_id == series.id,
                CatalogSeries.mangakol_slug == mangakol_slug,
            )
        )
        if existing is None:
            self.session.add(
                CatalogSeries(series_id=series.id, mangakol_slug=mangakol_slug)
            )


def _prefix_or_substring(short: str, long_: str) -> bool:
    if long_.startswith(short):
        # word boundary: "athica" matches "athica yayinlari" but not "athica2x"
        if len(long_) == len(short):
            return True
        return long_[len(short)] in " ."
    return short in long_


def _names_related(a: str, b: str) -> bool:
    """True when two normalized publisher names look like the same entity:
    equal, or (both >= 3 chars) one is a word-prefix/substring of the other
    ("athica" vs "athica yayinlari").

    Turkish compounds that one source writes with an inner space
    ("komik seyler" vs "komiksleyler yayincilik") are compared again with
    all whitespace removed, so variant spellings of the same company are
    still consolidated instead of opening a twin publisher row.
    """
    if not a or not b:
        return False
    if a == b:
        return True
    if len(a) < _PUB_MIN_MATCH_LEN or len(b) < _PUB_MIN_MATCH_LEN:
        return False
    if _prefix_or_substring(a, b) or _prefix_or_substring(b, a):
        return True
    # Stripped comparison uses a plain prefix: removing the whitespace
    # destroys the word-boundary signal. Require a >= 6-char prefix whose
    # continuation is alphabetic, so "komikseyler" matches
    # "komikseyler yayincilik" but "athica" never matches "athica2x".
    sa, sb = a.replace(" ", ""), b.replace(" ", "")
    if sa != sb and len(sa) >= _PUB_MIN_MATCH_LEN and len(sb) >= _PUB_MIN_MATCH_LEN:
        sshort, slong = (sa, sb) if len(sa) <= len(sb) else (sb, sa)
        if (
            len(sshort) >= 6
            and slong.startswith(sshort)
            and slong[len(sshort)].isalpha()
        ):
            return True
    return False
