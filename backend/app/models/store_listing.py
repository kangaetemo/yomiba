from datetime import datetime

from sqlalchemy import Boolean, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

from decimal import Decimal

price: Mapped[Decimal] = mapped_column(
    Numeric(10, 2),
)


class StoreListing(Base):
    __tablename__ = "store_listings"

    id: Mapped[int] = mapped_column(primary_key=True)

    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volumes.id"),
        index=True,
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id"),
        index=True,
    )

    product_url: Mapped[str] = mapped_column(
        String(1000),
    )

    price: Mapped[float] = mapped_column(
        Numeric(10, 2),
    )

    in_stock: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
    )

    last_checked: Mapped[datetime] = mapped_column()

    volume: Mapped["Volume"] = relationship(
        back_populates="store_listings"
    )

    store: Mapped["Store"] = relationship(
        back_populates="listings"
    )

    price_history: Mapped[list["PriceHistory"]] = relationship(
        back_populates="listing",
        cascade="all, delete-orphan",
    )