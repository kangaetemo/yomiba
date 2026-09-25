"""Read-side business logic for the catalog API.

Route handlers stay thin: they validate input, call these functions, and map
the returned ORM objects / dataclasses onto Pydantic response models.
"""

from __future__ import annotations

from dataclasses import dataclass, field

from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from ..models import CatalogSeries, PriceHistory, Series, StoreListing, Volume
from ..normalization import normalize_text
from ..normalization.volume import UNNUMBERED_VOLUME


def _volume_order():
    """Order volumes numerically; unnumbered (boxes/sets) go last."""
    return (
        case((Volume.volume_number == UNNUMBERED_VOLUME, 1), else_=0),
        Volume.volume_number,
        Volume.id,
    )


@dataclass
class SeriesMatch:
    series: Series
    volume_count: int
    cover_url: str | None


@dataclass
class VolumeStats:
    best_price_cents: int | None
    store_count: int


@dataclass
class SeriesDetail:
    series: Series
    volumes: list[Volume]
    volume_stats: dict[int, VolumeStats] = field(default_factory=dict)
    cover_url: str | None = None


@dataclass
class VolumeDetail:
    volume: Volume
    listings: list[StoreListing]


@dataclass
class HistoryEntry:
    listing: StoreListing
    points: list[PriceHistory]


@dataclass
class PriceHistoryDetail:
    volume: Volume
    entries: list[HistoryEntry]


def search_series(session: Session, query: str) -> list[SeriesMatch]:
    """Match catalog series whose normalized title contains the query.

    Only series registered in the ``catalog_series`` manifest (i.e. pulled
    in by the Mangakol catalog sync) are searched. Products that store
    imports add but the catalog does not cover stay in the DB — with their
    listings and price history — but are not surfaced here.
    """
    query_key = normalize_text(query)
    if not query_key:
        return []

    # Escape LIKE wildcards so user input is matched literally.
    escaped = query_key.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    pattern = f"%{escaped}%"
    # Match the Turkish display title OR the original (foreign) title, so
    # e.g. "Tokyo Ghoul" finds the Turkish-edition series "Tokyo Gül".
    # (original_title NULL simply does not match.)
    catalog_ids = select(CatalogSeries.series_id).distinct()
    series_rows = session.scalars(
        select(Series)
        .where(
            or_(
                Series.normalized_title.like(pattern, escape="\\"),
                Series.original_title.like(pattern, escape="\\"),
            )
        )
        .where(Series.id.in_(catalog_ids))
        .order_by(Series.title, Series.id)
    ).all()
    if not series_rows:
        return []

    series_ids = [s.id for s in series_rows]
    volumes = session.scalars(
        select(Volume)
        .where(Volume.series_id.in_(series_ids))
        .order_by(*_volume_order())
    ).all()

    volumes_by_series: dict[int, list[Volume]] = {}
    for volume in volumes:
        volumes_by_series.setdefault(volume.series_id, []).append(volume)

    matches: list[SeriesMatch] = []
    for series in series_rows:
        series_volumes = volumes_by_series.get(series.id, [])
        cover = next((v.cover_url for v in series_volumes if v.cover_url), None)
        matches.append(
            SeriesMatch(series=series, volume_count=len(series_volumes), cover_url=cover)
        )
    return matches


def get_series(session: Session, series_id: int) -> SeriesDetail | None:
    series = session.get(Series, series_id)
    if series is None or not _is_catalog_series(session, series_id):
        return None

    volumes = session.scalars(
        select(Volume).where(Volume.series_id == series_id).order_by(*_volume_order())
    ).all()

    stats: dict[int, VolumeStats] = {}
    if volumes:
        listings = session.scalars(
            select(StoreListing).where(StoreListing.volume_id.in_([v.id for v in volumes]))
        ).all()
        listings_by_volume: dict[int, list[StoreListing]] = {}
        for listing in listings:
            listings_by_volume.setdefault(listing.volume_id, []).append(listing)
        for volume in volumes:
            stats[volume.id] = _volume_stats(listings_by_volume.get(volume.id, []))

    cover = next((v.cover_url for v in volumes if v.cover_url), None)
    return SeriesDetail(series=series, volumes=volumes, volume_stats=stats, cover_url=cover)


def _volume_stats(listings: list[StoreListing]) -> VolumeStats:
    """Best (lowest) current price + number of stores for a volume.

    In-stock listings are preferred; if every listing is out of stock the
    cheapest known price is reported so the page still shows information.
    """
    if not listings:
        return VolumeStats(best_price_cents=None, store_count=0)
    in_stock = [l.price for l in listings if l.in_stock and l.price is not None]
    if in_stock:
        best = min(in_stock)
    else:
        all_prices = [l.price for l in listings if l.price is not None]
        best = min(all_prices) if all_prices else None
    return VolumeStats(best_price_cents=best, store_count=len(listings))


def get_volume(session: Session, volume_id: int) -> VolumeDetail | None:
    volume = session.get(Volume, volume_id)
    if volume is None or not _is_catalog_series(session, volume.series_id):
        return None

    # Cheapest first; listings without a price go last.
    nulls_last = case((StoreListing.price.is_(None), 1), else_=0)
    listings = session.scalars(
        select(StoreListing)
        .where(StoreListing.volume_id == volume_id)
        .order_by(nulls_last, StoreListing.price, StoreListing.id)
    ).all()
    return VolumeDetail(volume=volume, listings=listings)


def get_price_history(session: Session, volume_id: int) -> PriceHistoryDetail | None:
    volume = session.get(Volume, volume_id)
    if volume is None or not _is_catalog_series(session, volume.series_id):
        return None

    listings = session.scalars(
        select(StoreListing).where(StoreListing.volume_id == volume_id)
    ).all()
    if not listings:
        return PriceHistoryDetail(volume=volume, entries=[])

    history = session.scalars(
        select(PriceHistory)
        .where(PriceHistory.listing_id.in_([l.id for l in listings]))
        .order_by(PriceHistory.listing_id, PriceHistory.checked_at, PriceHistory.id)
    ).all()

    by_listing: dict[int, list[PriceHistory]] = {}
    for point in history:
        by_listing.setdefault(point.listing_id, []).append(point)

    entries = [
        HistoryEntry(listing=listing, points=by_listing.get(listing.id, []))
        for listing in sorted(listings, key=lambda l: l.id)
    ]
    return PriceHistoryDetail(volume=volume, entries=entries)


def _is_catalog_series(session: Session, series_id: int) -> bool:
    return session.scalar(
        select(CatalogSeries.series_id).where(CatalogSeries.series_id == series_id).limit(1)
    ) is not None
