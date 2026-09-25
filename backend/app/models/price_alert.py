"""PriceAlert model.

A price alert is one user's condition on one volume: "notify me (in the
future notification phase) when the best price drops to or below
``threshold_price``".

Semantics:
  * ``threshold_price`` is stored as INTEGER CENTS (150 TRY = 15000), never
    a float — consistent with ``store_listings.price`` / ``price_history``.
  * At most one alert row per (user, volume); "one active alert" is
    therefore guaranteed by the unique constraint, and ``is_active`` lets a
    user pause / re-activate the single alert.
  * The alert condition for a future checker is: best price <= threshold.
    NOTHING in this codebase evaluates it — no scheduler, no background
    job, no notification exists yet (a later phase).
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow

class PriceAlert(Base):
    __tablename__ = "price_alerts"
    __table_args__ = (
        UniqueConstraint("user_id", "volume_id", name="uq_price_alert_user_volume"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Account that owns this alert.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Alert threshold in CENTS (e.g. 15000 = 150 TRY). Always > 0.
    threshold_price: Mapped[int] = mapped_column(Integer, nullable=False)
    #: Paused alerts keep their threshold but are ignored by future checkers.
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self):  # pragma: no cover
        return (
            f"<PriceAlert user={self.user_id} volume={self.volume_id} "
            f"threshold={self.threshold_price} active={self.is_active}>"
        )
