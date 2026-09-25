"""Collection state belongs to a user and a catalog volume."""

from datetime import datetime

from sqlalchemy import CheckConstraint, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class UserVolumeCollection(Base):
    __tablename__ = "user_volume_collections"
    __table_args__ = (
        UniqueConstraint("user_id", "volume_id", name="uq_collection_user_volume"),
        CheckConstraint("status IN ('owned', 'missing', 'wanted')", name="ck_collection_status"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    volume_id: Mapped[int] = mapped_column(ForeignKey("volumes.id", ondelete="CASCADE"), nullable=False, index=True)
    status: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, nullable=False)
