"""SeriesPopularity: how high a catalog series ranks in stores' bestseller lists."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Float, ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class SeriesPopularity(Base):
    __tablename__ = "series_popularity"

    series_id: Mapped[int] = mapped_column(ForeignKey("series.id", ondelete="CASCADE"), primary_key=True)
    bestseller_score: Mapped[float] = mapped_column(Float, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
