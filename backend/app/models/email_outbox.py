"""EmailOutbox: a queued e-mail (price alerts). Sent by services/mailer.py."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Integer, String, Text
from sqlalchemy.orm import Mapped, mapped_column

from ..database import Base
from ..utils import utcnow


class EmailOutbox(Base):
    __tablename__ = "email_outbox"

    id: Mapped[int] = mapped_column(primary_key=True)
    to_email: Mapped[str] = mapped_column(String(320), nullable=False)
    subject: Mapped[str] = mapped_column(String(300), nullable=False)
    body_text: Mapped[str] = mapped_column(Text, nullable=False)
    body_html: Mapped[str | None] = mapped_column(Text)
    kind: Mapped[str] = mapped_column(String(40), nullable=False)
    #: Unique per event ("price_alert:<id>:<timestamp>"): queuing twice is a no-op.
    ref: Mapped[str] = mapped_column(String(120), nullable=False, unique=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    next_attempt_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, default=utcnow)
    attempts: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    last_error: Mapped[str | None] = mapped_column(String(500))
