"""GET /admin/instagram/releases — data for the Instagram post drafts (admin).

The admin page (/admin/instagram) turns a date window of catalog releases
into a carousel: a cover slide, a store-by-store price comparison for a few
featured volumes, the full list and a closing slide. This returns the
volumes released in the window (same rows as /releases) with every current
in-stock offer, cheapest first, and the series' reader interest so the page
can pick the volumes to feature. Read-only; nothing here triggers a scrape.
"""

from __future__ import annotations

from datetime import date

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import require_admin
from ..database import get_db
from ..models import Store, StoreListing, Volume
from ..services.catalog_service import fresh_listing_condition
from ..utils import from_cents, utcnow
from .home import _release_query, _serialize_releases, reader_interest

router = APIRouter(tags=["instagram"], dependencies=[Depends(require_admin)])

#: Longest window one draft covers (a month of releases).
MAX_DAYS = 31


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
    volumes = _serialize_releases(session, rows)

    # A store has one listing per volume; fresh in-stock ones only, like
    # the prices shown on the site.
    offers: dict[int, list[dict]] = {}
    for volume_id, code, name, price in session.execute(
        select(StoreListing.volume_id, Store.code, Store.name, StoreListing.price)
        .join(Store, Store.id == StoreListing.store_id)
        .where(StoreListing.volume_id.in_([v["id"] for v in volumes]),
               StoreListing.in_stock.is_(True), StoreListing.price.isnot(None),
               fresh_listing_condition(session))
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
    return {"start": start.isoformat(), "end": end.isoformat(),
            "generated_at": utcnow().isoformat(), "volumes": volumes}
