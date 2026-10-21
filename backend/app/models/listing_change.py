"""ListingChange model.

One row per meaningful change an import made to a store listing: a new
listing, a price or stock change, a switch to another product of the same
store, or a removed listing. Written in the same transaction as the listing
itself, so the admin panel can show which volume changed at which store
during a price refresh without diffing snapshots afterwards. Unchanged
re-checks write nothing; rows older than the retention window are pruned.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class ListingChange(Base):
    __tablename__ = "listing_changes"
    __table_args__ = (Index("ix_listing_changes_created", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False
    )
    #: "new" | "update" | "product" | "removed"
    kind: Mapped[str] = mapped_column(String(10), nullable=False)
    #: Why, when it is not a plain search result: "recheck" (product page
    #: re-check), "gone" (store removed the product), or a drop reason.
    note: Mapped[str | None] = mapped_column(String(32))
    #: Prices in cents; None when the store showed no price.
    old_price: Mapped[int | None] = mapped_column(Integer)
    new_price: Mapped[int | None] = mapped_column(Integer)
    old_in_stock: Mapped[bool | None] = mapped_column(Boolean)
    new_in_stock: Mapped[bool | None] = mapped_column(Boolean)
    product_url: Mapped[str | None] = mapped_column(String(2000))

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ListingChange {self.kind} volume={self.volume_id} store={self.store_id}>"
