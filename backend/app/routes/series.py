"""GET /series/{id} — series detail with per-volume price summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import optional_user
from ..models import User
from ..normalization.volume import UNNUMBERED_VOLUME
from ..schemas.series import SeriesOut, SeriesVolumeOut
from ..services import catalog_service, collections_service, series_slugs
from ..utils import from_cents
from ..services.covers import cover_url

router = APIRouter(tags=["series"])


@router.get("/series/{series_ref}", response_model=SeriesOut)
def get_series_detail(
    series_ref: str,
    session: Session = Depends(get_db),
    user: User | None = Depends(optional_user),
) -> SeriesOut:
    # The public URL uses the slug; a bare number (old links) still works.
    series_id = series_slugs.series_id_for(session, series_ref)
    detail = catalog_service.get_series(session, series_id) if series_id is not None else None
    if detail is None:
        raise HTTPException(status_code=404, detail="Seri bulunamadı.")

    volumes = [
        SeriesVolumeOut(
            id=volume.id,
            number=None if volume.volume_number == UNNUMBERED_VOLUME else volume.volume_number,
            best_price=from_cents(detail.volume_stats[volume.id].best_price_cents),
            store_count=detail.volume_stats[volume.id].store_count,
            in_stock_count=detail.volume_stats[volume.id].in_stock_count,
            stale_count=detail.volume_stats[volume.id].stale_count,
            best_store=detail.volume_stats[volume.id].best_store,
            collection_status=collections_service.get_volume_status(session, user.id if user else None, volume.id),  # type: ignore[arg-type]
            cover_url=cover_url(volume.cover_key),
            release_date=volume.release_date,
        )
        for volume in detail.volumes
    ]

    return SeriesOut(
        id=detail.series.id,
        title=detail.series.title,
        publisher=detail.series.publisher.name,
        slug=series_slugs.slug_for(session, detail.series.id),
        author=detail.series.author,
        cover_url=detail.cover_url,
        volumes=volumes,
    )
