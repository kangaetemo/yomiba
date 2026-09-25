"""Price-alert service: manage the single per-volume price alert.

Commit behavior mirrors :mod:`collections_service`: the service owns the
write and commits; routes pass the authenticated user ID explicitly.

Single-row upsert semantics (one ``PriceAlert`` row per user+volume):

  * PUT with a threshold  -> create the alert, or update the existing row's
    threshold; in both cases the alert is ACTIVE (setting a price expresses
    intent to be alerted, and a paused alert is re-activated this way).
  * PUT with only ``is_active`` -> pause / re-activate the existing alert
    without touching its threshold.
  * DELETE -> remove the alert.

IMPORTANT: this service only stores the condition. Nothing evaluates it —
the "best price <= threshold" check, any scheduler and any notification
delivery belong to future phases.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import PriceAlert, Volume
from ..utils import utcnow


def get_price_alert(session: Session, volume_id: int, user_id: int) -> PriceAlert | None:
    """Return the user's alert for a volume, or ``None`` when there is none.

    The volume must exist (callers 404 before reaching this in practice;
    the check here keeps the service safe when used directly).
    """
    if session.get(Volume, volume_id) is None:
        return None
    return session.scalar(
        select(PriceAlert).where(
            PriceAlert.user_id == user_id,
            PriceAlert.volume_id == volume_id,
        )
    )


def upsert_price_alert(
    session: Session,
    volume_id: int,
    user_id: int,
    threshold_price: int | None = None,
    is_active: bool | None = None,
) -> PriceAlert | None:
    """Create or update the user's single alert for a volume.

    ``threshold_price`` is in CENTS and must be positive when provided.
    Raises ``ValueError`` when no alert exists yet and no threshold is
    given (there is nothing to update). Returns the stored alert, or
    ``None`` when the volume does not exist.
    """
    if session.get(Volume, volume_id) is None:
        return None
    if threshold_price is not None and threshold_price <= 0:
        raise ValueError("threshold_price must be a positive integer (cents)")

    alert = session.scalar(
        select(PriceAlert).where(
            PriceAlert.user_id == user_id,
            PriceAlert.volume_id == volume_id,
        )
    )

    if alert is None:
        if threshold_price is None:
            raise ValueError("threshold_price is required to create an alert")
        alert = PriceAlert(
            user_id=user_id,
            volume_id=volume_id,
            threshold_price=threshold_price,
            is_active=True if is_active is None else is_active,
        )
        session.add(alert)
    else:
        if threshold_price is not None:
            alert.threshold_price = threshold_price
            # Providing a threshold (re)set activates the alert, including
            # a previously paused one.
            alert.is_active = True if is_active is None else is_active
        elif is_active is not None:
            alert.is_active = is_active
        alert.updated_at = utcnow()

    session.commit()
    return alert


def delete_price_alert(session: Session, volume_id: int, user_id: int) -> bool | None:
    """Delete the user's alert for a volume (idempotent).

    Returns ``True`` when there is (now) no alert, or ``None`` when the
    volume does not exist.
    """
    if session.get(Volume, volume_id) is None:
        return None
    alert = session.scalar(
        select(PriceAlert).where(
            PriceAlert.user_id == user_id,
            PriceAlert.volume_id == volume_id,
        )
    )
    if alert is not None:
        session.delete(alert)
        session.commit()
    return True
