"""Stock alerts ("stoğa girince haber ver"): one per user and volume.

PUT sets the alert, or sets a fired one again (clears ``triggered_at``);
DELETE removes it. services/restocks.py fires it after a price refresh as
soon as a store has the volume in stock. The service commits.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import StockAlert
from ..utils import utcnow


def get_stock_alert(session: Session, volume_id: int, user_id: int) -> StockAlert | None:
    return session.scalar(select(StockAlert).where(
        StockAlert.user_id == user_id, StockAlert.volume_id == volume_id))


def set_stock_alert(session: Session, volume_id: int, user_id: int) -> StockAlert:
    alert = get_stock_alert(session, volume_id, user_id)
    if alert is None:
        alert = StockAlert(user_id=user_id, volume_id=volume_id, created_at=utcnow())
        session.add(alert)
    else:
        alert.created_at, alert.triggered_at = utcnow(), None
    session.commit()
    return alert


def delete_stock_alert(session: Session, volume_id: int, user_id: int) -> None:
    alert = get_stock_alert(session, volume_id, user_id)
    if alert is not None:
        session.delete(alert)
        session.commit()
