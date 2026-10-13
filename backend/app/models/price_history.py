"""PriceHistory model.

Records price/stock/product changes and one successful observation per day.
Frequent unchanged polls do not duplicate points. Daily observations provide
bounded freshness and coverage for market-price comparisons.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String
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
    # Legacy points have no stock/product evidence. New observations retain
    # it, so a sold-out price or a different printing cannot become a deal.
    in_stock: Mapped[bool | None] = mapped_column(Boolean)
    product_url: Mapped[str | None] = mapped_column(String(2000))
    checked_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )

    listing: Mapped[StoreListing] = relationship(back_populates="history")

    def __repr__(self) -> str:  # pragma: no cover
        return f"<PriceHistory id={self.id} listing_id={self.listing_id} price={self.price}>"
