"""GET /me/* — the signed-in user's own collection, wishlist and alerts.

Read-only lists across all volumes (per-volume endpoints stay the write
path). Every query is filtered by the authenticated user's id; nothing here
accepts a user id from the request.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..auth import require_user
from ..database import get_db
from ..models import PriceAlert, Publisher, Series, StoreListing, User, UserVolumeCollection, Volume, WishlistItem
from ..normalization.volume import UNNUMBERED_VOLUME
from ..utils import from_cents
from ..services import series_slugs
from ..services.covers import cover_url

router = APIRouter(prefix="/me", tags=["me"])


class MyVolumeOut(BaseModel):
    volume_id: int
    volume_number: int | None
    series_id: int
    series_slug: str = ""
    series_title: str
    publisher: str
    cover_url: str | None = None
    best_price: float | None = None


class MyCollectionItemOut(MyVolumeOut):
    status: str
    updated_at: datetime


class MyWishlistItemOut(MyVolumeOut):
    added_at: datetime


class MyPriceAlertOut(MyVolumeOut):
    threshold_price: int
    is_active: bool
    updated_at: datetime


def _volume_fields(session: Session, volume_ids: list[int]) -> dict[int, dict]:
    if not volume_ids:
        return {}
    rows = session.execute(
        select(Volume, Series.title, Publisher.name)
        .join(Series, Series.id == Volume.series_id)
        .join(Publisher, Publisher.id == Series.publisher_id)
        .where(Volume.id.in_(volume_ids))
    ).all()
    best = dict(session.execute(
        select(StoreListing.volume_id, func.min(StoreListing.price))
        .where(StoreListing.volume_id.in_(volume_ids), StoreListing.in_stock.is_(True),
               StoreListing.price.isnot(None))
        .group_by(StoreListing.volume_id)
    ).all())
    slugs = series_slugs.slugs_for(session, [v.series_id for v, _, _ in rows])
    out = {}
    for volume, series_title, publisher in rows:
        phantom = volume.volume_number == UNNUMBERED_VOLUME
        out[volume.id] = {
            "volume_id": volume.id,
            "volume_number": None if phantom else volume.volume_number,
            "series_id": volume.series_id,
            "series_slug": slugs[volume.series_id],
            "series_title": series_title,
            "publisher": publisher,
            "cover_url": cover_url(volume.cover_key),
            # Legacy phantom prices are frozen; never present them as current.
            "best_price": None if phantom else from_cents(best.get(volume.id)),
        }
    return out


def _sort_key(item: BaseModel):
    number = item.volume_number if item.volume_number is not None else 10**6
    return (item.series_title.casefold(), item.series_id, number, item.volume_id)


@router.get("/collection", response_model=list[MyCollectionItemOut])
def my_collection(session: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = session.scalars(select(UserVolumeCollection).where(UserVolumeCollection.user_id == user.id)).all()
    fields = _volume_fields(session, [r.volume_id for r in rows])
    items = [MyCollectionItemOut(**fields[r.volume_id], status=r.status, updated_at=r.updated_at)
             for r in rows if r.volume_id in fields]
    return sorted(items, key=_sort_key)


@router.get("/wishlist", response_model=list[MyWishlistItemOut])
def my_wishlist(session: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = session.scalars(select(WishlistItem).where(WishlistItem.user_id == user.id)).all()
    fields = _volume_fields(session, [r.volume_id for r in rows])
    items = [MyWishlistItemOut(**fields[r.volume_id], added_at=r.created_at)
             for r in rows if r.volume_id in fields]
    return sorted(items, key=_sort_key)


@router.get("/price-alerts", response_model=list[MyPriceAlertOut])
def my_price_alerts(session: Session = Depends(get_db), user: User = Depends(require_user)):
    rows = session.scalars(select(PriceAlert).where(PriceAlert.user_id == user.id)).all()
    fields = _volume_fields(session, [r.volume_id for r in rows])
    items = [MyPriceAlertOut(**fields[r.volume_id], threshold_price=r.threshold_price,
                             is_active=r.is_active, updated_at=r.updated_at)
             for r in rows if r.volume_id in fields]
    return sorted(items, key=_sort_key)
