"""GET /volume/{id} and GET /volume/{id}/price-history."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.orm import Session

from ..database import get_db
from ..models import Volume
from ..normalization.volume import UNNUMBERED_VOLUME
from ..schemas.price_alert import PriceAlertDetail, PriceAlertIn, PriceAlertOut
from ..schemas.price_history import HistoryListingOut, HistoryPointOut, PriceHistoryOut
from ..schemas.volume import (
    SeriesRefOut,
    VolumeCollectionStatusIn,
    VolumeOut,
    VolumeStoreOut,
)
from ..schemas.wishlist import WishlistOut
from ..services import (
    catalog_service,
    collections_service,
    price_alerts_service,
    wishlist_service,
)
from ..utils import from_cents

router = APIRouter(tags=["volume"])


def _build_volume_out(session: Session, volume_id: int) -> VolumeOut | None:
    """Map a volume (and its store listings) onto the API schema.

    Returns ``None`` when the volume does not exist. Shared by the detail
    and collection-status endpoints so the two cannot drift apart.
    """
    detail = catalog_service.get_volume(session, volume_id)
    if detail is None:
        return None
    volume = detail.volume
    stores = [
        VolumeStoreOut(
            store=listing.store.name,
            price=from_cents(listing.price),
            currency="TRY",
            stock=listing.in_stock,
            product_url=listing.product_url,
            image_url=listing.image_url,
            last_checked=listing.last_checked,
        )
        for listing in detail.listings
    ]
    return VolumeOut(
        id=volume.id,
        number=None if volume.volume_number == UNNUMBERED_VOLUME else volume.volume_number,
        cover_url=volume.cover_url,
        series=SeriesRefOut(
            id=volume.series.id,
            title=volume.series.title,
            publisher=volume.series.publisher.name,
        ),
        stores=stores,
        collection_status=volume.collection_status,  # type: ignore[arg-type]
    )


@router.get("/volume/{volume_id}", response_model=VolumeOut)
def get_volume_detail(
    volume_id: int,
    session: Session = Depends(get_db),
) -> VolumeOut:
    out = _build_volume_out(session, volume_id)
    if out is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")
    return out


@router.patch(
    "/volume/{volume_id}/collection-status", response_model=VolumeOut
)
def set_volume_collection_status(
    volume_id: int,
    payload: VolumeCollectionStatusIn,
    session: Session = Depends(get_db),
) -> VolumeOut:
    """Mark a volume owned / missing / wanted, or clear it with ``null``."""
    try:
        updated = collections_service.set_volume_status(
            session, volume_id, payload.status
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if updated is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")
    return _build_volume_out(session, volume_id)


@router.get("/volume/{volume_id}/price-history", response_model=PriceHistoryOut)
def get_volume_price_history(
    volume_id: int,
    session: Session = Depends(get_db),
) -> PriceHistoryOut:
    detail = catalog_service.get_price_history(session, volume_id)
    if detail is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")

    listings = [
        HistoryListingOut(
            listing_id=entry.listing.id,
            store=entry.listing.store.name,
            points=[
                HistoryPointOut(
                    price=from_cents(point.price) or 0.0,
                    checked_at=point.checked_at,
                )
                for point in entry.points
            ],
        )
        for entry in detail.entries
    ]
    return PriceHistoryOut(volume_id=detail.volume.id, listings=listings)


# ---------------------------------------------------------------------------
# Wishlist (independent of collection_status)
# ---------------------------------------------------------------------------
@router.get("/volume/{volume_id}/wishlist", response_model=WishlistOut)
def get_wishlist(
    volume_id: int,
    session: Session = Depends(get_db),
) -> WishlistOut:
    state = wishlist_service.is_wishlisted(session, volume_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")
    return WishlistOut(volume_id=volume_id, wishlisted=state)


@router.post("/volume/{volume_id}/wishlist", response_model=WishlistOut)
def add_to_wishlist(
    volume_id: int,
    session: Session = Depends(get_db),
) -> WishlistOut:
    """Add to wishlist; idempotent (re-adding creates no duplicate)."""
    state = wishlist_service.add_to_wishlist(session, volume_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")
    return WishlistOut(volume_id=volume_id, wishlisted=state)


@router.delete("/volume/{volume_id}/wishlist", response_model=WishlistOut)
def remove_from_wishlist(
    volume_id: int,
    session: Session = Depends(get_db),
) -> WishlistOut:
    """Remove from wishlist; idempotent (removing twice is safe)."""
    state = wishlist_service.remove_from_wishlist(session, volume_id)
    if state is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")
    return WishlistOut(volume_id=volume_id, wishlisted=not state)


# ---------------------------------------------------------------------------
# Price alerts (storage only; no checker / notification in this phase)
# ---------------------------------------------------------------------------
def _alert_out(volume_id: int, alert) -> PriceAlertOut:

    detail = (
        PriceAlertDetail(
            id=alert.id,
            threshold_price=alert.threshold_price,
            is_active=alert.is_active,
            updated_at=alert.updated_at,
        )
        if alert is not None
        else None
    )
    return PriceAlertOut(volume_id=volume_id, alert=detail)


@router.get("/volume/{volume_id}/price-alert", response_model=PriceAlertOut)
def get_price_alert(
    volume_id: int,
    session: Session = Depends(get_db),
) -> PriceAlertOut:
    if session.get(Volume, volume_id) is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")
    return _alert_out(volume_id, price_alerts_service.get_price_alert(session, volume_id))


@router.put("/volume/{volume_id}/price-alert", response_model=PriceAlertOut)
def set_price_alert(
    volume_id: int,
    payload: PriceAlertIn,
    session: Session = Depends(get_db),
) -> PriceAlertOut:
    """Create or update the single per-volume alert (threshold in cents)."""
    if session.get(Volume, volume_id) is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")
    try:
        alert = price_alerts_service.upsert_price_alert(
            session, volume_id, payload.threshold_price, payload.is_active
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _alert_out(volume_id, alert)


@router.delete("/volume/{volume_id}/price-alert", response_model=PriceAlertOut)
def delete_price_alert(
    volume_id: int,
    session: Session = Depends(get_db),
) -> PriceAlertOut:
    """Delete the alert; idempotent."""
    if session.get(Volume, volume_id) is None:
        raise HTTPException(status_code=404, detail="Cilt bulunamadı.")
    price_alerts_service.delete_price_alert(session, volume_id)
    return PriceAlertOut(volume_id=volume_id, alert=None)
