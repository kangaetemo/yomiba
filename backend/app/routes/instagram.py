"""Data for the Instagram post drafts on the admin page (/admin/instagram).

* GET /admin/instagram/releases: the weekly carousel (a cover slide, a
  slide per featured volume, the full list and a closing slide; no prices,
  so the post does not read as an ad). Returns the volumes released in the
  window (same rows as /releases) with the series' credits and status and
  its reader interest, so the page can pick the volumes to feature. Offers
  are included too (cheapest first) for the admin's picker.
* GET /admin/instagram/launch: the "site açıldı" announcement carousel.
  Catalog counts for the cover, and the volumes whose price differs most
  between stores (three or more fresh in-stock offers, not all the same
  price) as candidates for the "same book, different price" example slide.

Read-only; nothing here triggers a scrape.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import CatalogSeries, Publisher, Series, Store, StoreListing, Volume
from ..services.catalog_service import fresh_listing_condition, public_volume_condition
from ..utils import from_cents, utcnow
from .home import _catalog_ids, _release_query, _serialize_releases, reader_interest

router = APIRouter(tags=["instagram"], dependencies=[Depends(require_admin)])

#: Longest window one draft covers (a month of releases).
MAX_DAYS = 31
#: Example candidates for the launch post, and the offers each needs.
LAUNCH_EXAMPLES = 15
LAUNCH_MIN_OFFERS = 3


def _offer_condition(session: Session):
    """Fresh in-stock listings with a price, like the prices on the site."""
    return (StoreListing.in_stock.is_(True), StoreListing.price.isnot(None),
            fresh_listing_condition(session))


def _with_offers(session: Session, volumes: list[dict]) -> list[dict]:
    """Add every store's offer (a store has one listing per volume), cheapest
    first, and the series' reader interest."""
    offers: dict[int, list[dict]] = {}
    for volume_id, code, name, price in session.execute(
        select(StoreListing.volume_id, Store.code, Store.name, StoreListing.price)
        .join(Store, Store.id == StoreListing.store_id)
        .where(StoreListing.volume_id.in_([v["id"] for v in volumes]), *_offer_condition(session))
        .order_by(StoreListing.volume_id, StoreListing.price, Store.name)
    ):
        offers.setdefault(volume_id, []).append(
            {"store": name, "store_code": code, "price": from_cents(price)})

    interest = reader_interest(session)
    for v in volumes:
        v["offers"] = offers.get(v["id"], [])
        v["lowest_price"] = v["offers"][0]["price"] if v["offers"] else None
        v["in_stock_offers"] = len(v["offers"])
        v["interest"] = round(interest.get(v["series_id"], 0.0), 2)
    return volumes


@router.get("/admin/instagram/releases")
def instagram_releases(
    start: date = Query(),
    end: date = Query(),
    session: Session = Depends(get_db),
) -> dict:
    if end < start or (end - start).days >= MAX_DAYS:
        raise HTTPException(status_code=422, detail=f"start..end must be 1-{MAX_DAYS} days")
    rows = session.execute(
        _release_query()
        .where(Volume.release_date >= start, Volume.release_date <= end)
        .order_by(Volume.release_date, Volume.id)
    ).all()
    volumes = _with_offers(session, _serialize_releases(session, rows))
    series = {sid: (author, jp, tr) for sid, author, jp, tr in session.execute(
        select(Series.id, Series.author, Series.jp_status, Series.tr_status)
        .where(Series.id.in_({v["series_id"] for v in volumes}))
    )}
    for v in volumes:
        v["author"], v["jp_status"], v["tr_status"] = series.get(v["series_id"], (None, None, None))
    return {"start": start.isoformat(), "end": end.isoformat(),
            "generated_at": utcnow().isoformat(), "volumes": volumes}


@router.get("/admin/instagram/launch")
def instagram_launch(session: Session = Depends(get_db)) -> dict:
    catalog_volume = (Volume.series_id.in_(_catalog_ids()), Volume.volume_number >= 0,
                      public_volume_condition())
    offers = select(StoreListing).where(*_offer_condition(session)).subquery()
    stats = {
        "series": session.scalar(select(func.count(func.distinct(CatalogSeries.series_id)))) or 0,
        "volumes": session.scalar(select(func.count(Volume.id)).where(*catalog_volume)) or 0,
        "publishers": session.scalar(
            select(func.count(func.distinct(Series.publisher_id)))
            .where(Series.id.in_(_catalog_ids()))) or 0,
        "stores": session.scalar(select(func.count(func.distinct(offers.c.store_id)))) or 0,
        "offers": session.scalar(select(func.count()).select_from(offers)) or 0,
    }

    spread = (
        select(offers.c.volume_id,
               (func.max(offers.c.price) - func.min(offers.c.price)).label("spread"),
               func.min(offers.c.price).label("min_price"), func.count().label("stores"))
        .group_by(offers.c.volume_id)
        .having(func.count() >= LAUNCH_MIN_OFFERS, func.max(offers.c.price) > func.min(offers.c.price))
        .subquery()
    )
    rows = session.execute(
        select(Volume, Series.title, Publisher.name, spread.c.min_price, spread.c.stores)
        .join(spread, spread.c.volume_id == Volume.id)
        .join(Series, Series.id == Volume.series_id)
        .join(Publisher, Publisher.id == Series.publisher_id)
        .where(*catalog_volume)
        .order_by(spread.c.spread.desc(), Volume.id)
        .limit(LAUNCH_EXAMPLES)
    ).all()
    examples = _with_offers(session, _serialize_releases(session, rows))
    return {"generated_at": utcnow().isoformat(), "stats": stats, "examples": examples}
