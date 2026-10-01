"""GET /home — the home page shelves, computed from catalog data only.

* ``popular_series``: catalog series with at least one in-stock offer,
  ranked by time-weighted reader interest (wishlist + collection rows; the
  last RECENT_DAYS count RECENT_WEIGHT times), then by in-stock offers PER
  VOLUME (so long series do not win just by length), then by total offers.
  The price shown is the lowest current in-stock price of any volume.
* ``new_volumes``: volumes by their LOCAL release date from the catalog
  source (Mangakol "Yayın Tarihi (Yerel)"), newest first, never in the
  future. Volumes without a known date are not listed.
* ``one_shots``: single-volume series that Mangakol marks completed both
  in Japan and in Turkey (Look Back, Soichi) — one book and the story is
  done. Binding variants ("Soichi (Bez Cilt)") are left out; in-stock
  titles first, then by reader interest and offers.
* ``stats``: catalog / store / offer counts for the hero.

Read-only; nothing here triggers a scrape.
"""

from __future__ import annotations

from datetime import date, timedelta

from fastapi import APIRouter, Depends, Query
from sqlalchemy import case, func, select
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
from ..services import series_slugs
from ..services.covers import cover_url
from ..utils import from_cents, utcnow

router = APIRouter(tags=["home"])


def _catalog_ids():
    return select(CatalogSeries.series_id).distinct()


def _series_covers(session: Session, series_ids: list[int]) -> dict[int, str]:
    """First numbered volume with a cover, per series."""
    covers: dict[int, str] = {}
    rows = session.execute(
        select(Volume.series_id, Volume.cover_key)
        .where(Volume.series_id.in_(series_ids), Volume.cover_key.isnot(None),
               Volume.volume_number >= 0)
        .order_by(Volume.series_id, Volume.volume_number)
    )
    for series_id, key in rows:
        covers.setdefault(series_id, cover_url(key))
    return covers


#: Reader activity within this window counts RECENT_WEIGHT times, so the
#: shelf follows what readers are into now, not what they added years ago.
RECENT_DAYS = 30
RECENT_WEIGHT = 3.0


def reader_interest(session: Session) -> dict[int, float]:
    """Time-weighted reader interest per series: wishlist rows (by when they
    were added) plus collection rows (by their last status change)."""
    cutoff = utcnow() - timedelta(days=RECENT_DAYS)
    interest: dict[int, float] = {}
    for model, stamp in ((WishlistItem, WishlistItem.created_at),
                         (UserVolumeCollection, UserVolumeCollection.updated_at)):
        weight = case((stamp >= cutoff, RECENT_WEIGHT), else_=1.0)
        for sid, score in session.execute(
            select(Volume.series_id, func.sum(weight))
            .select_from(model).join(Volume, Volume.id == model.volume_id)
            .group_by(Volume.series_id)
        ):
            interest[sid] = interest.get(sid, 0.0) + float(score or 0)
    return interest


@router.get("/home")
def home(
    popular: int = Query(default=8, ge=1, le=24),
    one_shot: int = Query(default=8, ge=1, le=48),
    new: int = Query(default=10, ge=1, le=30),
    session: Session = Depends(get_db),
) -> dict:
    catalog = _catalog_ids()
    real = Volume.volume_number >= 0

    # -- popular series ---------------------------------------------------------
    interest = reader_interest(session)
    offers = session.execute(
        select(Volume.series_id, func.count(StoreListing.id), func.min(StoreListing.price))
        .join(StoreListing, StoreListing.volume_id == Volume.id)
        .where(Volume.series_id.in_(catalog), real, StoreListing.in_stock.is_(True),
               StoreListing.price.isnot(None))
        .group_by(Volume.series_id)
    ).all()
    volume_counts = dict(session.execute(
        select(Volume.series_id, func.count())
        .where(Volume.series_id.in_([r[0] for r in offers]), real)
        .group_by(Volume.series_id)
    ).all())

    def rank(row):
        sid, offer_count, _ = row
        # Offers per volume: how easy the series is to buy, without long
        # series winning merely by having many volumes.
        availability = offer_count / max(1, volume_counts.get(sid, 0))
        return (-interest.get(sid, 0.0), -availability, -offer_count, sid)

    ranked = sorted(offers, key=rank)[:popular]
    popular_ids = [r[0] for r in ranked]
    series_rows = {
        s.id: (s, p) for s, p in session.execute(
            select(Series, Publisher.name).join(Publisher, Publisher.id == Series.publisher_id)
            .where(Series.id.in_(popular_ids))
        )
    }
    covers = _series_covers(session, popular_ids)
    popular_series = []
    slugs = series_slugs.slugs_for(session, popular_ids)
    for sid, offer_count, min_price in ranked:
        series, publisher = series_rows[sid]
        popular_series.append({
            "id": sid,
            "slug": slugs[sid],
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
    new_slugs = series_slugs.slugs_for(session, [v.series_id for v, *_ in new_rows])
    new_volumes = [
        {
            "id": v.id,
            "series_id": v.series_id,
            "series_slug": new_slugs[v.series_id],
            "series_title": title,
            "publisher": publisher,
            "number": v.volume_number,
            "covers_from": v.covers_from,
            "covers_to": v.covers_to,
            "cover_url": cover_url(v.cover_key) or fallback_covers.get(v.series_id),
            "release_date": v.release_date.isoformat(),
            "lowest_price": from_cents(min_price),
            "in_stock_offers": stores or 0,
        }
        for v, title, publisher, min_price, stores in new_rows
    ]

    one_shots = _one_shots(session, interest, one_shot)

    stats = {
        "series": session.scalar(select(func.count(func.distinct(CatalogSeries.series_id)))) or 0,
        "stores": session.scalar(
            select(func.count(func.distinct(StoreListing.store_id)))) or 0,
        "offers": session.scalar(
            select(func.count(StoreListing.id)).where(StoreListing.price.isnot(None))) or 0,
    }
    return {"popular_series": popular_series, "one_shots": one_shots,
            "new_volumes": new_volumes, "stats": stats}


def _one_shots(session: Session, interest: dict[int, float], limit: int) -> list[dict]:
    real = Volume.volume_number >= 0
    main_catalog = select(CatalogSeries.series_id).where(~CatalogSeries.mangakol_slug.contains("~"))
    single = (
        select(Volume.series_id).where(real).group_by(Volume.series_id)
        .having(func.count(Volume.id) == 1)
    )
    rows = session.execute(
        select(Series, Publisher.name).join(Publisher, Publisher.id == Series.publisher_id)
        .where(Series.id.in_(main_catalog), Series.id.in_(single),
               Series.jp_status == "completed", Series.tr_status == "completed")
    ).all()
    ids = [s.id for s, _ in rows]
    offers = {
        sid: (count, price) for sid, count, price in session.execute(
            select(Volume.series_id, func.count(StoreListing.id), func.min(StoreListing.price))
            .join(StoreListing, StoreListing.volume_id == Volume.id)
            .where(Volume.series_id.in_(ids), real, StoreListing.in_stock.is_(True),
                   StoreListing.price.isnot(None))
            .group_by(Volume.series_id)
        )
    }

    def rank(row):
        sid = row[0].id
        count = offers.get(sid, (0, None))[0]
        return (count == 0, -interest.get(sid, 0.0), -count, row[0].title)

    picked = sorted(rows, key=rank)[:limit]
    covers = _series_covers(session, [s.id for s, _ in picked])
    shot_slugs = series_slugs.slugs_for(session, [s.id for s, _ in picked])
    return [
        {
            "id": series.id,
            "slug": shot_slugs[series.id],
            "title": series.title,
            "publisher": publisher,
            "author": series.author,
            "cover_url": covers.get(series.id),
            "volume_count": 1,
            "in_stock_offers": offers.get(series.id, (0, None))[0],
            "lowest_price": from_cents(offers.get(series.id, (0, None))[1]),
        }
        for series, publisher in picked
    ]
