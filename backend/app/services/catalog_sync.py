"""Mangakol catalog sync — the identity/merge strategy, implemented.

Mangakol is a CATALOG source (series + published volumes), not a price
store. This service maps its data onto the existing ``Series``/``Volume``
model and merges matching publisher editions instead of duplicating them.

IDENTITY / MERGE STRATEGY
-------------------------
Source identity of one mangakol manga entry: (cleaned title, local
publisher) — nothing else (mangakol has no ISBNs).

1. **Title cleaning.** Mangakol display titles may carry the local
   publisher as a trailing parenthesized suffix: "Berserk (Athica)". The
   suffix is stripped ONLY when its content fuzzily matches the entry's
   own "Yerel Yayıncı" value (so meaningful parentheticals are never
   lost). The result is normalized with :func:`normalize_text` into the
   series key.
2. **Publisher resolution (data-driven, no hardcoded mappings).**
   * no "Yerel Yayıncı" on the page -> the existing "Bilinmiyor"
     fallback publisher;
   * otherwise exact match on ``normalize_text(name)`` against existing
     publishers, else a prefix/containment match (both sides >= 3
     characters: "Athica" -> "Athica Yayınları");
   * still nothing -> a new publisher is created with the scraped name.
   Before the manga loop runs, a consolidation pass merges publisher
   rows that fuzzy-match each other (same real company named
   differently by different sources, e.g. "Dex" vs "Dex Yayınevi")
   into the most complete name — series re-pointed or, on same-title
   collisions, merged volume-by-volume (add-only) — so every company
   has exactly one publisher row and lookups are stable.
3. **Series.** Primary lookup by ``(publisher_id, normalized_title)`` —
   the database unique constraint guarantees AT MOST ONE such row, so
   there is never an ambiguous merge and never a title-only match (a
   "Berserk" under Dark Horse is a different row and is never touched
   by a mangakol "Berserk (Athica)" entry). Fallbacks (mirroring
   ``ImportService``'s single-candidate rule):
   * no publisher-specific row, the source publisher is REAL, and
     EXACTLY ONE series with this title exists under the reserved
     "Bilinmiyor" publisher -> merge into it (the edition's publisher
     was unknown; the row keeps its publisher, never rewritten);
   * no publisher-specific row and the source has no publisher ->
     merge when exactly one series with this title exists (any
     publisher), otherwise create under "Bilinmiyor".
   * found -> **merge**: only missing volumes are added;
   * not found -> created (title = cleaned title, publisher as
     resolved, unique slug per publisher).
   Publisher resolution picks the most COMPLETE existing row when
   several rows refer to the same real company (the DB can hold both
   "Athica" and "Athica Yayınları" from different stores; the longer
   normalized name is preferred).
4. **Volumes.** Found by ``(series_id, volume_number)`` (unique
   constraint). Missing numbers are created; unnumbered items map to
   ``UNNUMBERED_VOLUME`` (-1) — at most one per series (constraint).
   Covers are backfilled only when the volume currently has none.
5. **Catalog scope.** Ordinary merges preserve existing series attributes
   and volumes. Every entry returned by Mangakol is catalog-eligible.
6. **Idempotent.** Re-running the sync re-hits the same rows (find or
   create everywhere) and adds nothing new; the unique constraints make
   duplicates impossible.
7. **Isolation.** A failing manga (HTTP error, blocked page, parse
   issue) is logged with debug info and counted; it never aborts the
   rest of the sync — same philosophy as ``ImportService``.
8. **Catalog manifest.** Every synced entry records its series in the
   ``catalog_series`` table (series_id + mangakol slug). Search and detail
   endpoints require this membership. Store imports attach listings only
   to existing catalog editions.

The service owns the database writes; the scraper
(``app.scrapers.mangakol``) stays DB-independent.
"""

from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import (
    CatalogSeries,
    Publisher,
    PublisherAlias,
    Series,
    StoreListing,
    UserVolumeCollection,
    WishlistItem,
    PriceAlert,
    Volume,
)
from ..normalization import normalize_publisher, normalize_text
from ..normalization.isbn import is_foreign_isbn
from ..normalization.text import slugify
from ..scrapers.mangakol import (
    CatalogManga,
    CatalogVolumeDetails,
    MangakolCatalogScraper,
)
from ..utils import utcnow
from .phantom_review import has_personal_rows, merge_volume_rows

logger = logging.getLogger("yomiba.catalog")

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
    covers_backfilled: int = 0
    #: Publisher rows merged into a more complete name for the same company.
    publishers_merged: int = 0
    #: Series absorbed into a same-title series under the merged publisher.
    series_absorbed: int = 0
    #: Volumes folded into an existing volume of the merged series.
    volumes_merged: int = 0
    #: Volume pages opened for ISBNs / ISBNs stored / ISBNs already held by
    #: another volume (never moved; see ``isbn_conflict_details``).
    isbn_pages: int = 0
    isbns_added: int = 0
    isbn_conflicts: int = 0
    isbn_conflict_details: list[str] = field(default_factory=list)
    #: Legacy "Cilt -1" rows of the same series folded into the volume
    #: whose catalog ISBN they held (not counted as conflicts).
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
        try:
            refs = self.scraper.list_manga()
        except Exception:
            self.scraper.close()
            raise
        report.manga_total = len(refs)
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

        try:
            for ref in refs:
                report.manga_scanned += 1
                try:
                    manga = self.scraper.fetch_manga(ref.slug)
                except Exception as exc:  # noqa: BLE001 - isolation by design
                    logger.exception(
                        "catalog sync: failed to fetch /manga/%s", ref.slug
                    )
                    report.manga_failed += 1
                    report.errors.append(f"{ref.slug}: {type(exc).__name__}: {exc}")
                    continue
                counts_before = (
                    report.series_created, report.series_merged,
                    report.volumes_added, report.covers_backfilled,
                )
                try:
                    with self.session.begin_nested():
                        series = self._merge_manga(manga, report)
                except Exception as exc:  # noqa: BLE001 - isolation by design
                    (
                        report.series_created, report.series_merged,
                        report.volumes_added, report.covers_backfilled,
                    ) = counts_before
                    logger.exception(
                        "catalog sync: failed to merge /manga/%s", ref.slug
                    )
                    report.manga_failed += 1
                    report.errors.append(
                        f"{ref.slug}: {type(exc).__name__}: {exc}"
                    )
                    continue
                self.session.commit()
                if series is not None:
                    try:
                        self._backfill_isbns(series, manga, report)
                    except Exception:  # noqa: BLE001 - ISBNs are best effort
                        logger.exception("catalog sync: ISBN backfill failed for /manga/%s", ref.slug)
                        self.session.rollback()
        finally:
            self.scraper.close()
        # A successful sync must represent exactly the live snapshot. Stale
        # slug identity changes require reconciliation; do not delete a
        # Series or guess an edition match during an ordinary sync.
        manifest_slugs = list(self.session.scalars(select(CatalogSeries.mangakol_slug)))
        live_slugs = {ref.slug for ref in refs}
        missing = live_slugs - set(manifest_slugs)
        stale = set(manifest_slugs) - live_slugs
        if missing:
            report.errors.append(f"live slugs missing from manifest: {sorted(missing)}")
        if stale:
            report.errors.append(f"stale manifest slugs require reconciliation: {sorted(stale)}")
        if len(manifest_slugs) != len(set(manifest_slugs)):
            report.errors.append("duplicate Mangakol slugs in catalog manifest")
        return report

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
        # Credits follow the catalog source (a page without them never erases).
        for attr in ("author", "illustrator"):
            value = (getattr(manga, attr, None) or "").strip()[:200]
            if value and getattr(series, attr) != value:
                setattr(series, attr, value)

        for volume in manga.volumes:
            number = volume.number if volume.number is not None else -1
            existing = self.session.scalar(
                select(Volume).where(
                    Volume.series_id == series.id,
                    Volume.volume_number == number,
                )
            )
            covers = getattr(volume, "covers", None)
            if existing is not None:
                if existing.cover_url is None and volume.cover_url:
                    existing.cover_url = volume.cover_url
                    report.covers_backfilled += 1
                # The omnibus span follows the catalog source (only a known
                # span overwrites; a page without one never erases it).
                if covers and (existing.covers_from, existing.covers_to) != covers:
                    existing.covers_from, existing.covers_to = covers
                continue
            self.session.add(
                Volume(
                    series_id=series.id,
                    volume_number=number,
                    cover_url=volume.cover_url,
                    covers_from=covers[0] if covers else None,
                    covers_to=covers[1] if covers else None,
                )
            )
            report.volumes_added += 1
        return series

    def _backfill_isbns(self, series: Series, manga: CatalogManga, report: CatalogSyncReport) -> None:
        """Read the ISBN of released volumes that have none from their own
        Mangakol page, within the per-sync request budget.

        The ISBN is the importer's first matching key: a store product with
        a known ISBN resolves to its volume whatever its title says. Never
        moves an ISBN: one held by another volume (a wrong earlier match or
        a legacy row) is only reported. Commits per volume.
        """
        fetch_details = getattr(self.scraper, "fetch_volume_details", None)
        fetch_isbn = getattr(self.scraper, "fetch_volume_isbn", None)
        if fetch_details is None and fetch_isbn is None:
            return
        recheck = utcnow() - timedelta(days=7)
        for cv in manga.volumes:
            if self._isbn_budget <= 0:
                return
            if cv.number is None or not getattr(cv, "url", None) or not getattr(cv, "released", True):
                continue
            volume = self.session.scalar(
                select(Volume).where(Volume.series_id == series.id, Volume.volume_number == cv.number)
            )
            if volume is None:
                continue
            checked = volume.details_checked_at
            if checked is not None and checked.tzinfo is None:
                checked = checked.replace(tzinfo=timezone.utc)
            # Read once (ISBN + page count + release date); a page without
            # an ISBN yet is re-read weekly. Pre-details rows that already
            # have an ISBN are read once more for their details.
            # A foreign ISBN (an old title match stored e.g. VIZ's English
            # Naruto 11 on Cilt 11) does not count: the catalog's replaces it.
            trusted_isbn = volume.isbn and not is_foreign_isbn(volume.isbn)
            if checked is not None and (trusted_isbn or checked > recheck):
                continue
            self._isbn_budget -= 1
            report.isbn_pages += 1
            try:
                if fetch_details is not None:
                    details = fetch_details(cv.url)
                else:
                    details = CatalogVolumeDetails(isbn=fetch_isbn(cv.url))
            except Exception:  # noqa: BLE001 - one page must not stop the sync
                logger.warning("catalog sync: volume page failed for %s", cv.url)
                continue
            volume.details_checked_at = utcnow()
            if details is not None:
                if details.page_count:
                    volume.page_count = details.page_count
                if details.release_date:
                    volume.release_date = details.release_date
            self.session.commit()
            isbn = details.isbn if details is not None else None
            if not isbn or trusted_isbn or is_foreign_isbn(isbn):
                continue
            if volume.isbn:  # foreign ISBN from an old match: drop it
                logger.info("catalog sync: replacing foreign ISBN %s on %s Cilt %s with %s",
                            volume.isbn, series.title, cv.number, isbn)
                volume.isbn = None
                self.session.flush()
            holder = self.session.scalar(select(Volume).where(Volume.isbn == isbn))
            if holder is None:
                volume.isbn = isbn
                self.session.commit()
                report.isbns_added += 1
                continue
            if holder.id == volume.id:
                continue
            note = ""
            if holder.series_id == series.id and holder.volume_number < 0:
                # Legacy unnumbered row ("Cilt -1") of THIS series holding
                # the catalog ISBN: the same book. The ISBN is the identity
                # proof, so fold it into the real volume (listings + price
                # history move). Personal rows keep it for manual review.
                if not has_personal_rows(self.session, holder.id):
                    merge_volume_rows(self.session, holder.id, volume.id)
                    self.session.commit()
                    report.isbns_added += 1
                    report.isbn_phantoms_merged += 1
                    logger.info("catalog sync: merged legacy volume %s into %s Cilt %s (ISBN %s)",
                                holder.id, series.title, cv.number, isbn)
                    continue
                note = " (kullanıcı verisi var, elle birleştirilmeli)"
            report.isbn_conflicts += 1
            holder_series = self.session.get(Series, holder.series_id)
            detail = (
                f"{series.title} Cilt {cv.number}: ISBN {isbn} zaten "
                f"{holder_series.title if holder_series else holder.series_id} "
                f"Cilt {holder.volume_number} üzerinde{note}"
            )
            logger.warning("catalog sync: %s", detail)
            if len(report.isbn_conflict_details) < 500:
                report.isbn_conflict_details.append(detail)

    @staticmethod
    def _original_title_key(raw: str) -> str:
        """Normalized search key for a detail page's original-title h2.

        mangakol sometimes lists the same title twice with different
        lettering (``One-Punch Man | One Punch-Man | ワンパンマン``). Each
        ``|`` part is normalized separately, empties (e.g. CJK-only parts
        after diacritic/CJK folding) are dropped, duplicates collapse, and
        distinct parts are joined with a single space.
        """
        seen: set[str] = set()
        parts: list[str] = []
        for part in raw.split("|"):
            key = normalize_text(part)
            if key and key not in seen:
                seen.add(key)
                parts.append(key)
        return " ".join(parts)

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
        """Merge publisher rows that refer to the same real company.

        Different sources name the same company differently (store
        imports: "Dex Yayınevi"; mangakol: "Dex"), and the database can
        hold both rows. Left alone, the same manga can end up under two
        publisher rows — a silent duplicate that breaks merge lookups.
        Each fuzzy-related group is merged into its most complete
        (longest normalized name, then lowest id) member:

        * series without a same-title twin under the keeper are
          re-pointed to the keeper (slug kept unique per publisher);
        * series whose title already exists under the keeper are merged
          volume-by-volume (add-only: unique numbers re-pointed,
          colliding numbers keep the keeper's volume, its listings are
          moved to it, covers backfilled) and then deleted;
        * the absorbed publisher row is deleted once it holds no series.

        Additive with respect to data: no listing, volume number, or
        series title is ever lost or overwritten.
        """
        pubs = list(self.session.scalars(select(Publisher)).all())
        parent = list(range(len(pubs)))

        def find(i: int) -> int:
            while parent[i] != i:
                parent[i] = parent[parent[i]]
                i = parent[i]
            return i

        for i in range(len(pubs)):
            for j in range(i + 1, len(pubs)):
                a, b = pubs[i].normalized_name, pubs[j].normalized_name
                if a != b and _names_related(a, b):
                    ri, rj = find(i), find(j)
                    if ri != rj:
                        parent[rj] = ri

        groups: dict[int, list[Publisher]] = {}
        for i, pub in enumerate(pubs):
            groups.setdefault(find(i), []).append(pub)

        for members in groups.values():
            if len(members) < 2:
                continue
            keeper = max(
                members, key=lambda p: (len(p.normalized_name), -p.id)
            )
            for other in members:
                if other.id == keeper.id:
                    continue
                self._merge_publisher_into(other, keeper, report)
                report.publishers_merged += 1
                logger.info(
                    "catalog sync: merged publisher %r into %r",
                    other.name, keeper.name,
                )

    def _merge_publisher_into(
        self, absorbed: Publisher, keeper: Publisher, report: CatalogSyncReport
    ) -> None:
        keeper_series = {
            s.normalized_title: s
            for s in self.session.scalars(
                select(Series).where(Series.publisher_id == keeper.id)
            ).all()
        }
        for sr in list(
            self.session.scalars(
                select(Series).where(Series.publisher_id == absorbed.id)
            ).all()
        ):
            twin = keeper_series.get(sr.normalized_title)
            if twin is not None and twin.id != sr.id:
                self._merge_series_into(sr, twin, report)
                # Flush re-pointed volumes BEFORE deleting the series: the
                # Series.volumes relationship cascades deletes, and a
                # not-yet-flushed re-point would look "still attached" to
                # the cascade's lazy load.
                self.session.flush()
                self.session.delete(sr)
                report.series_absorbed += 1
                keeper_series.pop(sr.normalized_title, None)
                logger.info(
                    "catalog sync: merged series %r (%s) into series %s",
                    sr.title, absorbed.name, twin.id,
                )
            else:
                sr.publisher_id = keeper.id
                # delete-orphan semantics: an object removed from (or
                # repointed away from) a loaded collection is deleted
                # unless it is re-attached to the new parent's loaded
                # collection in the same session — do exactly that.
                if sr in absorbed.series:
                    absorbed.series.remove(sr)
                if sr not in keeper.series:
                    keeper.series.append(sr)
                # (publisher_id, slug) is unique: de-collide if the keeper
                # already holds the same slug under a different title.
                clash = self.session.scalar(
                    select(Series.id).where(
                        Series.publisher_id == keeper.id,
                        Series.slug == sr.slug,
                        Series.id != sr.id,
                    )
                )
                if clash is not None:
                    sr.slug = self._unique_slug(
                        keeper.id, sr.normalized_title, exclude_id=sr.id
                    )
        self.session.flush()  # re-points must be visible to the check below
        remaining = self.session.scalar(
            select(Series.id).where(Series.publisher_id == absorbed.id).limit(1)
        )
        if remaining is None:
            self.session.delete(absorbed)

    def _merge_series_into(
        self, absorbed: Series, keeper: Series, report: CatalogSyncReport
    ) -> None:
        """Fold ``absorbed``'s volumes into ``keeper`` (add-only)."""
        # The absorbed series may already belong to the catalog. Preserve
        # every slug before deleting it, or the merged keeper could become
        # invisible while its volumes and listings survive.
        for row in self.session.scalars(
            select(CatalogSeries).where(CatalogSeries.series_id == absorbed.id)
        ).all():
            self._mark_catalog_series(keeper, row.mangakol_slug)
            self.session.delete(row)
        self.session.flush()
        keeper_volumes = {
            v.volume_number: v
            for v in self.session.scalars(
                select(Volume).where(Volume.series_id == keeper.id)
            ).all()
        }
        for vol in list(
            self.session.scalars(
                select(Volume).where(Volume.series_id == absorbed.id)
            ).all()
        ):
            target = keeper_volumes.get(vol.volume_number)
            if target is None:
                vol.series_id = keeper.id
                # delete-orphan: move the volume between the two parents'
                # loaded collections so the unit of work sees a move, not
                # an orphan (see _merge_publisher_into above).
                if vol in absorbed.volumes:
                    absorbed.volumes.remove(vol)
                if vol not in keeper.volumes:
                    keeper.volumes.append(vol)
                keeper_volumes[vol.volume_number] = vol
                continue
            # Number collision: the keeper's volume row survives. Move its
            # listings (a store listing both editions keeps the keeper's
            # row — the most recently imported data), backfill the cover,
            # then delete the absorbed volume row.
            for listing in list(vol.listings):
                already = self.session.scalar(
                    select(StoreListing.id).where(
                        StoreListing.volume_id == target.id,
                        StoreListing.store_id == listing.store_id,
                    )
                )
                if already is None:
                    listing.volume_id = target.id
                    vol.listings.remove(listing)
                    target.listings.append(listing)
                else:
                    logger.warning(
                        "catalog sync: dropped duplicate listing %s for "
                        "store %s during series merge (kept existing)",
                        listing.id, listing.store_id,
                    )
                    self.session.delete(listing)
                    vol.listings.remove(listing)
            if target.cover_url is None and vol.cover_url:
                target.cover_url = vol.cover_url
                report.covers_backfilled += 1
            self._move_personal_rows(vol.id, target.id)
            self.session.delete(vol)
            # Drop it from the absorbed series' loaded collection so the
            # later series delete's cascade does not re-issue the DELETE.
            if vol in absorbed.volumes:
                absorbed.volumes.remove(vol)
            report.volumes_merged += 1

    def _move_personal_rows(self, source_id: int, target_id: int) -> None:
        """Preserve user data when catalog dedup absorbs a volume.

        An incompatible conflict is safer to roll back than to guess which
        user's status or alert threshold should win.
        """
        for model in (UserVolumeCollection, WishlistItem, PriceAlert):
            for row in self.session.scalars(select(model).where(model.volume_id == source_id)).all():
                existing = self.session.scalar(select(model).where(
                    model.user_id == row.user_id, model.volume_id == target_id,
                ))
                if existing is None:
                    row.volume_id = target_id
                    continue
                if model is UserVolumeCollection and row.status != existing.status:
                    raise ValueError("conflicting collection states during volume merge")
                if model is PriceAlert and (row.threshold_price != existing.threshold_price or row.is_active != existing.is_active):
                    raise ValueError("conflicting price alerts during volume merge")
                self.session.delete(row)

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
