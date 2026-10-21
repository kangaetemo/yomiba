"""Send queued e-mails (``email_outbox``) over SMTP.

Provider-agnostic: Brevo, Resend, Mailgun, Gmail… all offer SMTP. Without
``SMTP_HOST`` nothing is sent and mails stay queued (sent once it is set).
A failed send is retried with growing delays, at most ``MAX_ATTEMPTS`` times.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from datetime import timedelta
from email.message import EmailMessage
from email.utils import make_msgid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import get_settings
from ..models import EmailOutbox
from ..utils import utcnow

logger = logging.getLogger("yomiba.mail")

MAX_ATTEMPTS = 8
BATCH = 50


def _connect(settings) -> smtplib.SMTP:
    if settings.smtp_security == "ssl":
        server: smtplib.SMTP = smtplib.SMTP_SSL(settings.smtp_host, settings.smtp_port, timeout=30,
                                                context=ssl.create_default_context())
    else:
        server = smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=30)
        if settings.smtp_security == "starttls":
            server.starttls(context=ssl.create_default_context())
    if settings.smtp_user:
        server.login(settings.smtp_user, settings.smtp_password)
    return server


def _message(row: EmailOutbox, sender: str) -> EmailMessage:
    msg = EmailMessage()
    msg["From"] = sender
    msg["To"] = row.to_email
    msg["Subject"] = row.subject
    msg["Message-ID"] = make_msgid(domain=sender.rsplit("@", 1)[-1].strip("> ") or "yomiba.com")
    msg.set_content(row.body_text)
    if row.body_html:
        msg.add_alternative(row.body_html, subtype="html")
    return msg


def send_pending(session: Session, *, connect=_connect, ids: list[int] | None = None) -> dict[str, int]:
    """Send due queued mails (only ``ids`` when given); commits after each.
    Returns counts."""
    settings = get_settings()
    counts = {"sent": 0, "failed": 0}
    if not settings.smtp_host:
        return counts
    now = utcnow()
    query = select(EmailOutbox).where(EmailOutbox.sent_at.is_(None), EmailOutbox.attempts < MAX_ATTEMPTS)
    if ids is not None:
        query = query.where(EmailOutbox.id.in_(ids))
    rows = list(session.scalars(query.order_by(EmailOutbox.id).limit(BATCH)))
    due = []
    for row in rows:
        at = row.next_attempt_at if row.next_attempt_at.tzinfo else row.next_attempt_at.replace(tzinfo=now.tzinfo)
        if at <= now:
            due.append(row)
    if not due:
        return counts
    try:
        server = connect(settings)
    except Exception as exc:  # noqa: BLE001 - provider down: retry later
        logger.warning("mail: SMTP connection failed: %s", exc)
        for row in due:
            _failed(row, f"bağlantı: {exc}")
        session.commit()
        counts["failed"] = len(due)
        return counts
    try:
        for row in due:
            try:
                server.send_message(_message(row, settings.mail_from))
                row.sent_at, row.last_error = utcnow(), None
                row.attempts += 1
                counts["sent"] += 1
            except Exception as exc:  # noqa: BLE001 - one bad address must not stop the rest
                _failed(row, str(exc))
                counts["failed"] += 1
            session.commit()
    finally:
        try:
            server.quit()
        except Exception:  # noqa: BLE001
            pass
    return counts


def _failed(row: EmailOutbox, error: str) -> None:
    row.attempts += 1
    row.last_error = error[:500]
    row.next_attempt_at = utcnow() + timedelta(minutes=5 * 2 ** min(row.attempts, 6))
