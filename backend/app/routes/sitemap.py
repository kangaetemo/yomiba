"""GET /sitemap — every public series and volume page, for sitemap.xml."""

from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy import not_, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import CatalogSeries, Volume
from ..normalization.volume import UNNUMBERED_VOLUME
from ..services import series_slugs
from ..services.catalog_service import legacy_phantom_condition, public_volume_condition

router = APIRouter(tags=["sitemap"])


@router.get("/sitemap")
def sitemap(session: Session = Depends(get_db)) -> dict:
    """Catalog series with the volume numbers their pages list.

    Same filters as the series page: released, not a legacy phantom. ``upcoming``
    says whether an announced volume exists (it keeps a single-volume series
    page from redirecting to its only volume)."""
    series_ids = sorted(set(session.scalars(select(CatalogSeries.series_id))))
    if not series_ids:
        return {"series": []}
    released: dict[int, list[int | None]] = {sid: [] for sid in series_ids}
    for sid, number in session.execute(
        select(Volume.series_id, Volume.volume_number)
        .where(Volume.series_id.in_(series_ids), public_volume_condition(include_announced=False),
               not_(legacy_phantom_condition()))
        .order_by(Volume.series_id, Volume.volume_number)
    ):
        n = None if number == UNNUMBERED_VOLUME else number
        if n not in released[sid]:
            released[sid].append(n)
    upcoming = set(session.scalars(
        select(Volume.series_id).where(
            Volume.series_id.in_(series_ids), Volume.catalog_present.is_(True),
            Volume.catalog_released.is_(False),
        )
    ))
    slugs = series_slugs.slugs_for(session, series_ids)
    return {"series": [
        {"slug": slugs[sid], "volumes": released[sid], "upcoming": sid in upcoming}
        for sid in series_ids
    ]}
