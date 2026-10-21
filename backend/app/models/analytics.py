"""First-party site analytics: one row per page view, store click, search
or page engagement, plus the daily salt behind the anonymous visitor hash.

No cookie and no lasting visitor id: ``visitor`` is a hash of IP + browser
with a salt that changes every day and is deleted afterwards, so a visitor
can be counted within a day but never followed across days. ``session`` is a
random id the browser keeps for one tab (sessionStorage). Catalog ids are
plain integers, not foreign keys: an event outlives a merged or removed
volume, and the report simply finds no title for it.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import Boolean, DateTime, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class AnalyticsEvent(Base):
    __tablename__ = "analytics_events"
    __table_args__ = (
        Index("ix_analytics_events_day_kind", "day", "kind"),
        Index("ix_analytics_events_session", "session"),
    )

    id: Mapped[int] = mapped_column(primary_key=True)
    ts: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow, index=True)
    #: Turkish local date ("2026-10-21") and hour (0-23), stored so reports
    #: group without database date functions.
    day: Mapped[str] = mapped_column(String(10), nullable=False)
    hour: Mapped[int] = mapped_column(Integer, nullable=False)
    #: pageview | outbound | search | engage
    kind: Mapped[str] = mapped_column(String(16), nullable=False)
    path: Mapped[str] = mapped_column(String(500), nullable=False, default="/")
    visitor: Mapped[str] = mapped_column(String(16), nullable=False)
    session: Mapped[str] = mapped_column(String(32), nullable=False)
    is_returning: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    logged_in: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    referrer_host: Mapped[str | None] = mapped_column(String(200))
    utm_source: Mapped[str | None] = mapped_column(String(100))
    utm_medium: Mapped[str | None] = mapped_column(String(100))
    utm_campaign: Mapped[str | None] = mapped_column(String(100))
    device: Mapped[str] = mapped_column(String(10), nullable=False, default="desktop")
    browser: Mapped[str] = mapped_column(String(30), nullable=False, default="Diğer")
    os: Mapped[str] = mapped_column(String(30), nullable=False, default="Diğer")
    country: Mapped[str | None] = mapped_column(String(2))
    series_id: Mapped[int | None] = mapped_column(Integer)
    volume_id: Mapped[int | None] = mapped_column(Integer)
    store_id: Mapped[int | None] = mapped_column(Integer)
    listing_id: Mapped[int | None] = mapped_column(Integer)
    #: Outbound: the clicked address (without our utm_* tags).
    target_url: Mapped[str | None] = mapped_column(String(2000))
    query: Mapped[str | None] = mapped_column(String(200))
    #: search: result count; engage: seconds the page was visible.
    value: Mapped[int | None] = mapped_column(Integer)


class AnalyticsSalt(Base):
    __tablename__ = "analytics_salts"

    day: Mapped[str] = mapped_column(String(10), primary_key=True)
    salt: Mapped[str] = mapped_column(String(64), nullable=False)
