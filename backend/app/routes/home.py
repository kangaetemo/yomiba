"""GET /home — the home page shelves, computed from catalog data only.

* ``popular_series``: catalog series ranked by reader interest (collection +
  wishlist rows) and then by how many in-stock store offers they have. The
  price shown is the lowest current in-stock price of any of its volumes.
* ``new_volumes``: volumes by their LOCAL release date from the catalog
  source (Mangakol "Yayın Tarihi (Yerel)"), newest first, never in the
  future. Volumes without a known date are not listed.
* ``stats``: catalog / store / offer counts for the hero.

Read-only; nothing here triggers a scrape.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import (
    CatalogSeries,
    Publisher,
    Series,
    StoreListing,
    UserVolumeCollection,
    Volume,
    WishlistItem,
)
from ..utils import from_cents

router = APIRouter(tags=["home"])


def _catalog_ids():
    return select(CatalogSeries.series_id).distinct()


def _series_covers(session: Session, series_ids: list[int]) -> dict[int, str]:
    """First numbered volume with a cover, per series."""
    covers: dict[int, str] = {}
    rows = session.execute(
        select(Volume.series_id, Volume.cover_url)
        .where(Volume.series_id.in_(series_ids), Volume.cover_url.isnot(None),
               Volume.volume_number >= 0)
        .order_by(Volume.series_id, Volume.volume_number)
    )
    for series_id, cover in rows:
        covers.setdefault(series_id, cover)
    return covers


@router.get("/home")
def home(
    popular: int = Query(default=8, ge=1, le=24),
    new: int = Query(default=10, ge=1, le=30),
    session: Session = Depends(get_db),
) -> dict:
    catalog = _catalog_ids()
    real = Volume.volume_number >= 0

    # -- popular series ---------------------------------------------------------
    interest = {
        sid: n for sid, n in session.execute(
            select(Volume.series_id, func.count())
            .select_from(WishlistItem).join(Volume, Volume.id == WishlistItem.volume_id)
            .group_by(Volume.series_id)
        )
    }
    for sid, n in session.execute(
        select(Volume.series_id, func.count())
        .select_from(UserVolumeCollection).join(Volume, Volume.id == UserVolumeCollection.volume_id)
        .group_by(Volume.series_id)
    ):
        interest[sid] = interest.get(sid, 0) + n

    offers = session.execute(
        select(Volume.series_id, func.count(StoreListing.id), func.min(StoreListing.price))
        .join(StoreListing, StoreListing.volume_id == Volume.id)
        .where(Volume.series_id.in_(catalog), real, StoreListing.in_stock.is_(True),
               StoreListing.price.isnot(None))
        .group_by(Volume.series_id)
    ).all()
    ranked = sorted(offers, key=lambda r: (-interest.get(r[0], 0), -r[1], r[0]))[:popular]
    popular_ids = [r[0] for r in ranked]
    series_rows = {
        s.id: (s, p) for s, p in session.execute(
            select(Series, Publisher.name).join(Publisher, Publisher.id == Series.publisher_id)
            .where(Series.id.in_(popular_ids))
        )
    }
    volume_counts = dict(session.execute(
        select(Volume.series_id, func.count()).where(Volume.series_id.in_(popular_ids), real)
        .group_by(Volume.series_id)
    ).all())
    covers = _series_covers(session, popular_ids)
    popular_series = []
    for sid, offer_count, min_price in ranked:
        series, publisher = series_rows[sid]
        popular_series.append({
            "id": sid,
            "title": series.title,
            "publisher": publisher,
            "author": series.author,
            "cover_url": covers.get(sid),
            "volume_count": volume_counts.get(sid, 0),
            "in_stock_offers": offer_count,
            "lowest_price": from_cents(min_price),
        })

    # -- new volumes (local release date) --------------------------------------------
    price_sub = (
        select(StoreListing.volume_id, func.min(StoreListing.price).label("min_price"),
               func.count(StoreListing.id).label("stores"))
        .where(StoreListing.in_stock.is_(True), StoreListing.price.isnot(None))
        .group_by(StoreListing.volume_id)
        .subquery()
    )
    new_rows = session.execute(
        select(Volume, Series.title, Publisher.name, price_sub.c.min_price, price_sub.c.stores)
        .join(Series, Series.id == Volume.series_id)
        .join(Publisher, Publisher.id == Series.publisher_id)
        .outerjoin(price_sub, price_sub.c.volume_id == Volume.id)
        .where(Volume.series_id.in_(catalog), real, Volume.release_date.isnot(None),
               Volume.release_date <= date.today())
        .order_by(Volume.release_date.desc(), Volume.id.desc())
        .limit(new)
    ).all()
    fallback_covers = _series_covers(session, list({v.series_id for v, *_ in new_rows}))
    new_volumes = [
        {
            "id": v.id,
            "series_id": v.series_id,
            "series_title": title,
            "publisher": publisher,
            "number": v.volume_number,
            "covers_from": v.covers_from,
            "covers_to": v.covers_to,
            "cover_url": v.cover_url or fallback_covers.get(v.series_id),
            "release_date": v.release_date.isoformat(),
            "lowest_price": from_cents(min_price),
            "in_stock_offers": stores or 0,
        }
        for v, title, publisher, min_price, stores in new_rows
    ]

    stats = {
        "series": session.scalar(select(func.count(func.distinct(CatalogSeries.series_id)))) or 0,
        "stores": session.scalar(
            select(func.count(func.distinct(StoreListing.store_id)))) or 0,
        "offers": session.scalar(
            select(func.count(StoreListing.id)).where(StoreListing.price.isnot(None))) or 0,
    }
    return {"popular_series": popular_series, "new_volumes": new_volumes, "stats": stats}
