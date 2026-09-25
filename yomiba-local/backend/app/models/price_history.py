"""PriceHistory model.

Appends a record each time a listing's price is created or changes. Unchanged
re-checks update the listing's ``last_checked`` but do NOT append history, so
the chart stays meaningful (no duplicate points).
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import DateTime, ForeignKey, Integer
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..utils import utcnow

if TYPE_CHECKING:
    from .store_listing import StoreListing


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)
    listing_id: Mapped[int] = mapped_column(
        ForeignKey("store_listings.id", ondelete="CASCADE"), nullable=False, index=True
    )
    #: Price in cents at the time of the check.
    price: Mapped[int] = mapped_column(Integer, nullable=False)
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )

    listing: Mapped[StoreListing] = relationship(back_populates="history")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PriceHistory id={self.id} listing_id={self.listing_id} price={self.price}>"
