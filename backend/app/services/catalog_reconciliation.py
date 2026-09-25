"""One-time, transaction-friendly reconciliation of a live Mangakol snapshot.

The caller owns the transaction. No catalog entity is deleted here: former
exclusions are reattached to their original Series, and a verified slug move
keeps the same Series and Volume identities.
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import CatalogExclusion, CatalogSeries, PublisherAlias, Series, Volume
from ..normalization import normalize_publisher, normalize_text
from ..normalization.text import slugify
from ..scrapers.mangakol import CatalogManga
from .catalog_sync import CatalogSyncReport, CatalogSyncService, _names_related


@dataclass(frozen=True)
class ReconciliationResult:
    restored_slugs: int
    moved_slugs: int
    new_slugs: int
    series_created: int
    volumes_added: int


def _same_catalog_edition(
    session: Session, series: Series, manga: CatalogManga
) -> bool:
    """Require publisher, franchise title, and volume continuity for a move."""
    if not manga.local_publisher or not manga.original_title:
        return False
    publisher = series.publisher
    incoming_publisher = normalize_publisher(manga.local_publisher)
    alias = session.scalar(
        select(PublisherAlias).where(
            PublisherAlias.normalized_alias == incoming_publisher
        )
    )
    publisher_matches = (
        incoming_publisher == publisher.normalized_name
        or (alias is not None and alias.publisher_id == publisher.id)
        or _names_related(incoming_publisher, publisher.normalized_name)
    )
    old_title = normalize_text(series.title)
    new_title = normalize_text(manga.title)
    old_original = series.original_title or ""
    new_original = normalize_text(manga.original_title.split("|")[0])
    old_numbers = set(session.scalars(
        select(Volume.volume_number).where(Volume.series_id == series.id)
    ))
    new_numbers = {v.number if v.number is not None else -1 for v in manga.volumes}
    return bool(
        publisher_matches and old_title and new_title.startswith(old_title)
        and old_original and new_original.startswith(old_original)
        and old_numbers and old_numbers <= new_numbers
    )


def reconcile_snapshot(
    session: Session,
    *,
    live_slugs: set[str],
    former_links: dict[str, int],
    missing_manga: dict[str, CatalogManga],
    slug_moves: dict[str, str],
) -> ReconciliationResult:
    """Apply an audited snapshot inside the caller's single transaction.

    ``former_links`` comes from a read-only pre-exclusion backup. Every
    existing Series ID is verified before its manifest link is restored.
    ``missing_manga`` includes detail pages for every unrepresented slug.
    """
    service = CatalogSyncService(session)
    report = CatalogSyncReport()
    initial_manifest = set(session.scalars(select(CatalogSeries.mangakol_slug)))
    missing = live_slugs - initial_manifest
    excluded = set(session.scalars(select(CatalogExclusion.mangakol_slug))) & live_slugs
    if set(former_links) != excluded:
        raise ValueError("former links do not cover exactly the live legacy exclusions")
    if set(missing_manga) != missing - excluded:
        raise ValueError("detail pages do not cover exactly the new live slugs")
    if set(slug_moves.values()) - set(missing_manga):
        raise ValueError("slug move target has no fetched detail page")

    for slug, series_id in former_links.items():
        if session.get(Series, series_id) is None:
            raise ValueError(f"former Series {series_id} for {slug} is missing")
        if session.scalar(select(CatalogSeries.series_id).where(
            CatalogSeries.series_id == series_id
        )) is not None:
            raise ValueError(f"former Series {series_id} is already in the manifest")
        session.add(CatalogSeries(series_id=series_id, mangakol_slug=slug))
        exclusion = session.get(CatalogExclusion, slug)
        if exclusion is None:
            raise ValueError(f"legacy exclusion {slug} disappeared")
        session.delete(exclusion)
    session.flush()

    for old_slug, new_slug in slug_moves.items():
        if old_slug in live_slugs:
            raise ValueError(f"old slug {old_slug} is still live")
        old_row = session.scalar(select(CatalogSeries).where(
            CatalogSeries.mangakol_slug == old_slug
        ))
        if old_row is None:
            raise ValueError(f"old slug {old_slug} is missing")
        series = session.get(Series, old_row.series_id)
        manga = missing_manga[new_slug]
        if series is None or not _same_catalog_edition(session, series, manga):
            raise ValueError(f"edition identity is unproven for {old_slug} -> {new_slug}")
        if session.scalar(select(CatalogSeries.series_id).where(
            CatalogSeries.mangakol_slug == new_slug
        )) is not None:
            raise ValueError(f"new slug {new_slug} is already represented")
        old_row.mangakol_slug = new_slug
        clean_title = service._clean_title(manga.title, manga.local_publisher)
        series.title = clean_title
        series.normalized_title = normalize_text(clean_title)
        series.slug = slugify(series.normalized_title)
        session.flush()
        service._merge_manga(manga, report)
        # The audited old JoJo cover URL is no longer served by Mangakol.
        # Refresh the moved entry's covers from its live detail page while
        # retaining the same Volume IDs and other volume data.
        for live_volume in manga.volumes:
            if not live_volume.cover_url:
                continue
            number = live_volume.number if live_volume.number is not None else -1
            existing_volume = session.scalar(select(Volume).where(
                Volume.series_id == series.id,
                Volume.volume_number == number,
            ))
            if existing_volume is not None:
                existing_volume.cover_url = live_volume.cover_url

    for slug in sorted(set(missing_manga) - set(slug_moves.values())):
        service._merge_manga(missing_manga[slug], report)
    session.flush()

    manifest_rows = list(session.scalars(select(CatalogSeries.mangakol_slug)))
    if set(manifest_rows) != live_slugs or len(manifest_rows) != len(live_slugs):
        raise ValueError("manifest does not equal the live Mangakol snapshot")
    if session.scalar(select(CatalogExclusion.mangakol_slug).where(
        CatalogExclusion.mangakol_slug.in_(live_slugs)
    ).limit(1)) is not None:
        raise ValueError("a live slug is still in legacy exclusions")
    return ReconciliationResult(
        restored_slugs=len(former_links), moved_slugs=len(slug_moves),
        new_slugs=len(missing_manga) - len(slug_moves),
        series_created=report.series_created, volumes_added=report.volumes_added,
    )
