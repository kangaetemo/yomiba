"""Audit data is separate from the catalogue. Evidence and decisions are append-only."""
from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import naive_utcnow


class IsbnAuditRun(Base):
    __tablename__ = "isbn_audit_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    status: Mapped[str] = mapped_column(String(20), default="RUNNING")
    requested_by: Mapped[int | None] = mapped_column(ForeignKey("users.id"))
    started_at: Mapped[datetime] = mapped_column(DateTime, default=naive_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime)
    total: Mapped[int] = mapped_column(default=0)
    processed: Mapped[int] = mapped_column(default=0)
    errors: Mapped[int] = mapped_column(default=0)
    lease: Mapped[str | None] = mapped_column(String(40))
    lease_until: Mapped[datetime | None] = mapped_column(DateTime)
    error: Mapped[str | None] = mapped_column(Text)


class IsbnAuditItem(Base):
    __tablename__ = "isbn_audit_items"
    run_id: Mapped[int] = mapped_column(ForeignKey("isbn_audit_runs.id"), primary_key=True)
    volume_id: Mapped[int] = mapped_column(ForeignKey("volumes.id"), primary_key=True)
    completed: Mapped[bool] = mapped_column(default=False)


class IsbnAuditResult(Base):
    __tablename__ = "isbn_audit_results"
    __table_args__ = (UniqueConstraint("run_id", "volume_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    run_id: Mapped[int] = mapped_column(ForeignKey("isbn_audit_runs.id"), index=True)
    volume_id: Mapped[int] = mapped_column(ForeignKey("volumes.id"), index=True)
    checked_at: Mapped[datetime] = mapped_column(DateTime, default=naive_utcnow)
    snapshot: Mapped[dict] = mapped_column(JSON)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(40))
    proposed_isbn: Mapped[str | None] = mapped_column(String(13))
    reason: Mapped[str] = mapped_column(Text)
    evidence: Mapped[list] = mapped_column(JSON)
    evidence_hash: Mapped[str] = mapped_column(String(64))


class IsbnReview(Base):
    __tablename__ = "isbn_reviews"
    volume_id: Mapped[int] = mapped_column(ForeignKey("volumes.id"), primary_key=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("isbn_audit_results.id"))
    version: Mapped[int] = mapped_column(default=1)
    workflow: Mapped[str] = mapped_column(String(30), default="REVIEW_PENDING", index=True)
    next_check_at: Mapped[datetime] = mapped_column(DateTime, index=True)


class IsbnDecision(Base):
    __tablename__ = "isbn_decisions"
    id: Mapped[int] = mapped_column(primary_key=True)
    volume_id: Mapped[int] = mapped_column(ForeignKey("volumes.id"), index=True)
    result_id: Mapped[int] = mapped_column(ForeignKey("isbn_audit_results.id"))
    review_version: Mapped[int] = mapped_column()
    admin_id: Mapped[int] = mapped_column(ForeignKey("users.id"))
    action: Mapped[str] = mapped_column(String(20))
    old_isbn: Mapped[str | None] = mapped_column(String(20))
    new_isbn: Mapped[str | None] = mapped_column(String(13))
    reason: Mapped[str] = mapped_column(Text)
    decided_at: Mapped[datetime] = mapped_column(DateTime, default=naive_utcnow)
    snapshot_hash: Mapped[str] = mapped_column(String(64))
    evidence_hash: Mapped[str] = mapped_column(String(64))
