"""GET /series/{id} — series detail with per-volume price summary."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..database import get_db
from ..auth import optional_user
from ..models import User, Volume, WishlistItem
from ..normalization.text import slugify
from ..normalization.volume import UNNUMBERED_VOLUME
from ..schemas.series import SeriesEditionOut, SeriesOut, SeriesVolumeOut
from ..services import catalog_service, collections_service, series_slugs, volume_descriptions
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

    wishlisted = set(session.scalars(select(WishlistItem.volume_id).where(
        WishlistItem.user_id == user.id,
        WishlistItem.volume_id.in_([v.id for v in detail.volumes]),
    ))) if user else set()
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
            wishlisted=volume.id in wishlisted,
            cover_url=cover_url(volume.cover_key),
            release_date=volume.release_date,
        )
        for volume in detail.volumes
    ]

    siblings = catalog_service.other_editions(session, detail.series.id)
    upcoming = [SeriesVolumeOut(
        id=v.id, number=None if v.volume_number == UNNUMBERED_VOLUME else v.volume_number,
        cover_url=cover_url(v.cover_key), release_date=v.release_date,
    ) for v in session.scalars(select(Volume).where(
        Volume.series_id == detail.series.id, Volume.catalog_present.is_(True),
        Volume.catalog_released.is_(False),
    ).order_by(Volume.volume_number))]
    sibling_ids = [s.id for s in siblings]
    intro = volume_descriptions.series_description(session, detail.series.id)
    offers = catalog_service.series_offer_summary(session, sibling_ids)
    sibling_slugs = series_slugs.slugs_for(session, sibling_ids)
    sibling_only = catalog_service.only_volume_numbers(session, sibling_ids)
    volume_counts = dict(session.execute(
        select(Volume.series_id, func.count()).where(
            Volume.series_id.in_(sibling_ids), Volume.volume_number >= 0,
            catalog_service.public_volume_condition(include_announced=False),
        ).group_by(Volume.series_id)
    ).all()) if sibling_ids else {}
    editions = [
        SeriesEditionOut(
            id=s.id,
            slug=sibling_slugs[s.id],
            title=s.title,
            publisher=s.publisher.name,
            volume_count=volume_counts.get(s.id, 0),
            only_volume=sibling_only.get(s.id),
            in_stock_offers=offers.get(s.id, (0, None))[0],
            lowest_price=from_cents(offers.get(s.id, (0, None))[1]),
        )
        for s in siblings
    ]

    return SeriesOut(
        id=detail.series.id,
        title=detail.series.title,
        publisher=detail.series.publisher.name,
        publisher_slug=slugify(detail.series.publisher.name),
        slug=series_slugs.slug_for(session, detail.series.id),
        author=detail.series.author,
        cover_url=detail.cover_url,
        volumes=volumes,
        upcoming_volumes=upcoming,
        editions=editions,
        description=intro[0] if intro else None,
        description_source=volume_descriptions.store_name(session, intro[1]) if intro else None,
        one_shot=(
            detail.series.jp_status == "completed"
            and detail.series.tr_status == "completed"
            and sum(1 for v in volumes if v.number is not None and v.number >= 0) == 1
        ),
    )
