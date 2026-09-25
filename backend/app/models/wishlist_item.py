"""WishlistItem model.

A wishlist item is one user's intent to track one volume. It is independent
of collection status (owned/missing/wanted): a volume can be both
tracked in the collection and on the wishlist at the same time.

There is at most one wishlist item per (user, volume), enforced by a unique
constraint so re-adding is impossible at the database level as well.
"""

from __future__ import annotations

from datetime import datetime
from sqlalchemy import DateTime, ForeignKey, Integer, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow

class WishlistItem(Base):
    __tablename__ = "wishlist_items"
    __table_args__ = (
        UniqueConstraint("user_id", "volume_id", name="uq_wishlist_user_volume"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    #: Account that owns this wishlist item.
    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True
    )
    volume_id: Mapped[int] = mapped_column(
        ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow
    )

    def __repr__(self):  # pragma: no cover
        return f"<WishlistItem user={self.user_id} volume={self.volume_id}>"
