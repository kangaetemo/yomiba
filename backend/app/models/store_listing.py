from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base

if TYPE_CHECKING:
    from app.models.price_history import PriceHistory
    from app.models.store import Store
    from app.models.volume import Volume


class StoreListing(Base):
    __tablename__ = "store_listings"

    id: Mapped[int] = mapped_column(primary_key=True)

    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volumes.id"),
        nullable=False,
        index=True,
    )

    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id"),
        nullable=False,
        index=True,
    )

    product_url: Mapped[str] = mapped_column(
        String(1000),
        nullable=False,
    )

    price: Mapped[Decimal] = mapped_column(
        Numeric(10, 2),
        nullable=False,
    )

    in_stock: Mapped[bool] = mapped_column(
        Boolean,
        default=False,
        nullable=False,
    )

    last_checked: Mapped[datetime] = mapped_column(
        DateTime,
        default=datetime.utcnow,
        nullable=False,
    )

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