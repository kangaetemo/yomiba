"""RestockEvent model.

One row each time a volume comes back after being sold out everywhere: no
store had it in stock (fresh, priced) for at least ``RESTOCK_MIN_GAP_DAYS``
and now one does. Written by services/restocks.py after a series' price
refresh; it feeds the "Tekrar stokta" shelf and page, the badge on series
and volume pages, the wishlist mails and the Instagram draft. A volume that
was never in stock before and is a recent release is NOT a restock (that is
"Yeni çıkanlar"); an older one that was only ever seen sold out is (a
reprint), with ``out_since`` None.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class RestockEvent(Base):
    __tablename__ = "restock_events"
    __table_args__ = (Index("ix_restock_events_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    #: When the volume was found in stock again.
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Last time any store had it in stock before the gap; None when it was
    #: never seen in stock before (first copies after a long sold-out spell).
    out_since: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: The cheapest store at that moment, and its price (cents).
    store_id: Mapped[int | None] = mapped_column(ForeignKey("stores.id", ondelete="SET NULL"))
    price: Mapped[int | None] = mapped_column(Integer)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<RestockEvent volume={self.volume_id} at={self.created_at}>"
