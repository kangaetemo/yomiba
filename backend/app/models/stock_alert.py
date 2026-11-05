"""StockAlert model.

"E-mail me when this volume is in stock again": one user, one volume, set on
a volume page while no store has it. Checked by services/restocks.py after
every price refresh of the series. It fires once, as soon as any store has
the volume fresh and in stock (no seven-day rule: the reader asked), and
then stays fired until the user sets it again.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class StockAlert(Base):
    __tablename__ = "stock_alerts"
    __table_args__ = (UniqueConstraint("user_id", "volume_id", name="uq_stock_alert_user_volume"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    #: When the mail was queued; None = still waiting for stock.
    triggered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<StockAlert user={self.user_id} volume={self.volume_id} fired={self.triggered_at}>"
