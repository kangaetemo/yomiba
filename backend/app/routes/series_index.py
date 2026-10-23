"""GET /series — every catalog series, for the A–Z page and publisher pages."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import not_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CatalogSeries, Publisher, Series, Volume
from ..normalization.text import slugify
from ..services import catalog_service, series_slugs
from ..services.covers import cover_url
from ..utils import from_cents

router = APIRouter(tags=["series"])


@router.get("/series")
def list_series(session: Session = Depends(get_db)) -> dict:
    """Catalog series that have a released or announced volume.

    ``only_volume`` is the volume number of a series whose page would just
    redirect to its single volume (same rule as the frontend's one shot
    links), so lists can link the volume directly."""
    rows = session.execute(
        select(Series, Publisher.name).join(Publisher, Publisher.id == Series.publisher_id)
        .where(Series.id.in_(select(CatalogSeries.series_id)))
    ).all()
    ids = [s.id for s, _ in rows]
    if not ids:
        return {"series": []}
    released = catalog_service.public_volume_condition(include_announced=False)
    numbers: dict[int, list[int]] = {}
    for sid, number in session.execute(
        select(Volume.series_id, Volume.volume_number)
        .where(Volume.series_id.in_(ids), released, Volume.volume_number >= 0)
    ):
        numbers.setdefault(sid, []).append(number)
    has_unnumbered = set(session.scalars(
        select(Volume.series_id).where(
            Volume.series_id.in_(ids), released, Volume.volume_number < 0,
            not_(catalog_service.legacy_phantom_condition()),
        )
    ))
    only = catalog_service.only_volume_numbers(session, ids)
    upcoming = set(session.scalars(
        select(Volume.series_id).where(
            Volume.series_id.in_(ids), Volume.catalog_present.is_(True),
            Volume.catalog_released.is_(False),
        )
    ))
    # First cover in volume order stands for the series.
    covers: dict[int, str] = {}
    for sid, key in session.execute(
        select(Volume.series_id, Volume.cover_key)
        .where(Volume.series_id.in_(ids), released, Volume.cover_key.isnot(None))
        .order_by(Volume.series_id, Volume.volume_number)
    ):
        covers.setdefault(sid, key)
    offers = catalog_service.series_offer_summary(session, ids)
    slugs = series_slugs.slugs_for(session, ids)

    items = []
    for series, publisher in rows:
        nums = numbers.get(series.id, [])
        if not nums and series.id not in has_unnumbered and series.id not in upcoming:
            continue
        items.append({
            "id": series.id,
            "slug": slugs[series.id],
            "title": series.title,
            "publisher": publisher,
            "publisher_slug": slugify(publisher),
            "author": series.author,
            "cover_url": cover_url(covers.get(series.id)),
            "volume_count": len(nums),
            "upcoming": series.id in upcoming,
            "only_volume": only.get(series.id),
            "in_stock_offers": offers.get(series.id, (0, None))[0],
            "lowest_price": from_cents(offers.get(series.id, (0, None))[1]),
        })
    return {"series": items}
