"""ImportRecord model.

One row per normalized query, tracking when that query was last imported
and how the attempt went. This is the freshness source of truth for the
DB-first search: a catalog result is "fresh" when the record's
``last_success_at`` is within the configured TTL.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, DateTime, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class ImportRecord(Base):
    __tablename__ = "import_records"

    id: Mapped[int] = mapped_column(primary_key=True)
    #: normalize_text(query) — "BERSERK" and "berserk" share one record.
    normalized_query: Mapped[str] = mapped_column(String(200), nullable=False, unique=True, index=True)
    #: Last raw query seen (for display/debugging).
    last_query: Mapped[str | None] = mapped_column(String(200))
    #: Last attempt of any kind (success / partial / failed / running).
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: Last attempt where at least one store succeeded. Freshness is based
    #: on this, not on ``last_attempt_at`` (a failed refresh must not make
    #: good data stale).
    last_success_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    #: "running" | "success" | "partial" | "failed"
    status: Mapped[str] = mapped_column(String(16), nullable=False, default="running")
    stores_ok: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    stores_failed: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    results_found: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    created: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    updated: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    #: Store errors of the last attempt ("amazon: <err> | dr: <err>"), if any.
    error: Mapped[str | None] = mapped_column(String(2000))
    #: Per-store rejection counts of the last attempt, e.g.
    #: ``{"bkm": {"no_series_match": 3}}``. Empty/None when nothing was
    #: rejected. Explains why a query found products but matched none.
    reasons: Mapped[dict | None] = mapped_column(JSON)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ImportRecord query={self.normalized_query!r} "
            f"status={self.status} success={self.last_success_at}>"
        )
