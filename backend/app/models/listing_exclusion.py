"""ListingExclusion: a store product an admin removed from a volume.

Some store products match a catalog volume by mistake (same title, a
store's wrong metadata). When an admin removes such a listing, the product
(store + product URL) is recorded here and the importer never attaches it
to any volume again.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class ListingExclusion(Base):
    __tablename__ = "listing_exclusions"
    __table_args__ = (
        UniqueConstraint("store_id", "product_url", name="uq_listing_exclusion_store_url"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    store_id: Mapped[int] = mapped_column(
        ForeignKey("stores.id", ondelete="CASCADE"), nullable=False, index=True
    )
    product_url: Mapped[str] = mapped_column(String(2000), nullable=False)
    #: The volume it was wrongly attached to (kept for the audit trail).
    volume_id: Mapped[int | None] = mapped_column(Integer)
    reason: Mapped[str | None] = mapped_column(String(300))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
