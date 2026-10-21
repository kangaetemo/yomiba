"""A visitor's "hatalı içerik" report about a series or volume page.

Catalog and user ids are plain integers, not foreign keys: a report outlives
a merged volume or a deleted account. ``reporter`` is a hash of the IP with
the day's analytics salt, enough to spot one sender flooding the list on a
given day but never stored as an IP.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Index, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class ContentReport(Base):
    __tablename__ = "content_reports"
    __table_args__ = (Index("ix_content_reports_status_created", "status", "created_at"),)

    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    #: price | stock | match | info | other
    category: Mapped[str] = mapped_column(String(16), nullable=False)
    message: Mapped[str] = mapped_column(Text, nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False)
    series_id: Mapped[int | None] = mapped_column(Integer)
    volume_id: Mapped[int | None] = mapped_column(Integer)
    store_id: Mapped[int | None] = mapped_column(Integer)
    user_id: Mapped[int | None] = mapped_column(Integer)
    reporter: Mapped[str] = mapped_column(String(16), nullable=False)
    #: new | resolved | dismissed
    status: Mapped[str] = mapped_column(String(10), nullable=False, default="new")
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
