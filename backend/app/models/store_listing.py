"""StoreListing model.

A StoreListing is one store's current listing for one volume. A volume can
have at most one listing per store (enforced by the unique constraint), which
is what makes upserts deterministic.

Price is stored as integer cents to avoid floating point drift; the API
layer converts it back to a decimal number.
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from ..database import Base
from ..utils import utcnow

if TYPE_CHECKING:
    from .price_history import PriceHistory
    from .store import Store
    from .volume import Volume


class StoreListing(Base):
    __tablename__ = "store_listings"
    __table_args__ = (
        UniqueConstraint("volume_id", "store_id", name="uq_listing_volume_store"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    #: Current price in cents. Nullable when a store shows no price.
    price: Mapped[int | None] = mapped_column(Integer)
    in_stock: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)
    #: When this listing was last checked by an import.
    last_checked: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )
    image_url: Mapped[str | None] = mapped_column(String(1000))

    volume: Mapped[Volume] = relationship(back_populates="listings")
    store: Mapped[Store] = relationship(back_populates="listings")
    history: Mapped[list[PriceHistory]] = relationship(
        back_populates="listing", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<StoreListing id={self.id} volume_id={self.volume_id} "
            f"store_id={self.store_id} price={self.price}>"
        )
