from datetime import datetime

from sqlalchemy import ForeignKey, Numeric
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

from decimal import Decimal

price: Mapped[Decimal] = mapped_column(
    Numeric(10, 2),
)


class PriceHistory(Base):
    __tablename__ = "price_history"

    id: Mapped[int] = mapped_column(primary_key=True)

    listing_id: Mapped[int] = mapped_column(
        ForeignKey("store_listings.id"),
        index=True,
    )

    price: Mapped[float] = mapped_column(
        Numeric(10, 2),
    )

    checked_at: Mapped[datetime] = mapped_column()

    listing: Mapped["StoreListing"] = relationship(
        back_populates="price_history"
    )