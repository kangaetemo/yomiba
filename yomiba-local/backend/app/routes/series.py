"""GET /series/{id} — series detail with per-volume price summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..normalization.volume import UNNUMBERED_VOLUME
from ..schemas.series import SeriesOut, SeriesVolumeOut
from ..services import catalog_service
from ..utils import from_cents

router = APIRouter(tags=["series"])


@router.get("/series/{series_id}", response_model=SeriesOut)
def get_series_detail(
    series_id: int,
    session: Session = Depends(get_db),
) -> SeriesOut:
    detail = catalog_service.get_series(session, series_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Seri bulunamadı.")

    volumes = [
        SeriesVolumeOut(
            id=volume.id,
            number=None if volume.volume_number == UNNUMBERED_VOLUME else volume.volume_number,
            best_price=from_cents(detail.volume_stats[volume.id].best_price_cents),
            store_count=detail.volume_stats[volume.id].store_count,
            collection_status=volume.collection_status,  # type: ignore[arg-type]
        )
        for volume in detail.volumes
    ]

    return SeriesOut(
        id=detail.series.id,
        title=detail.series.title,
        publisher=detail.series.publisher.name,
        slug=detail.series.slug,
        cover_url=detail.cover_url,
        volumes=volumes,
    )
