"""One-time links mailed to an account's address.

* ``verify``: "this is my address" after registering. The page also offers
  "I did not open this account", which deletes an unverified account that
  someone opened with another person's address.
* ``google_link``: link a Google account to an existing password account
  when Google's e-mail claim alone does not prove the mailbox (see
  ``google_auth.google_owns_mailbox``).

Mails go through ``email_outbox`` and are sent right away (``send_now``)
instead of waiting for the price refresh, which also drains the outbox.
"""

from __future__ import annotations

import logging
import secrets
from datetime import timedelta, timezone
from html import escape

from sqlalchemy import select, update
from sqlalchemy.engine import Engine
from sqlalchemy.orm import Session

from ..auth import token_digest
from ..config import get_settings
from ..models import EmailOutbox, EmailToken, User
from ..utils import utcnow

logger = logging.getLogger("yomiba.auth")

VERIFY_HOURS = 48
GOOGLE_LINK_HOURS = 1


def issue(session: Session, user: User, purpose: str, *, google_sub: str | None = None) -> str:
    """A fresh link token for ``user``; earlier unused ones of the same
    purpose stop working. Not committed."""
    now = utcnow()
    session.execute(update(EmailToken).where(
        EmailToken.user_id == user.id, EmailToken.purpose == purpose, EmailToken.used_at.is_(None),
    ).values(used_at=now))
    raw = secrets.token_urlsafe(32)
    hours = VERIFY_HOURS if purpose == "verify" else GOOGLE_LINK_HOURS
    session.add(EmailToken(user_id=user.id, purpose=purpose, token_hash=token_digest(raw),
                           google_sub=google_sub, created_at=now, expires_at=now + timedelta(hours=hours)))
    return raw


def lookup(session: Session, raw: str) -> EmailToken | None:
    """The unused, unexpired token row for ``raw``, else None."""
    if not raw:
        return None
    row = session.scalar(select(EmailToken).where(EmailToken.token_hash == token_digest(raw)))
    if row is None or row.used_at is not None:
        return None
    expires = row.expires_at.replace(tzinfo=row.expires_at.tzinfo or timezone.utc)
    return row if expires > utcnow() else None


def _link(raw: str) -> str:
    return f"{get_settings().site_url.rstrip('/')}/eposta-onay?t={raw}"


def _queue(session: Session, user: User, kind: str, subject: str, lines: list[str], url: str, button: str) -> EmailOutbox:
    now = utcnow()
    text = f"Merhaba {user.display_name},\n\n" + "\n\n".join(lines[:1]) + f"\n\n{button}: {url}\n\n" \
        + "\n\n".join(lines[1:]) + "\n\nYomiba"
    html = (f"<p>Merhaba {escape(user.display_name)},</p><p>{escape(lines[0])}</p>"
            f'<p><a href="{escape(url)}">{escape(button)}</a></p>'
            + "".join(f"<p>{escape(line)}</p>" for line in lines[1:]) + "<p>Yomiba</p>")
    row = EmailOutbox(to_email=user.email, subject=subject, body_text=text, body_html=html, kind=kind,
                      ref=f"{kind}:{user.id}:{secrets.token_hex(8)}", created_at=now, next_attempt_at=now)
    session.add(row)
    return row


def queue_verify(session: Session, user: User) -> EmailOutbox:
    url = _link(issue(session, user, "verify"))
    return _queue(session, user, "verify_email", "Yomiba: e-posta adresini doğrula", [
        "Yomiba hesabını açtığın için teşekkürler. Bu adresin sana ait olduğunu doğrulamak için bağlantıya tıkla.",
        f"Bağlantı {VERIFY_HOURS} saat geçerli.",
        "Bu hesabı sen açmadıysan bağlantıdaki sayfada “Ben açmadım” de; hesap silinir ve adresin "
        "serbest kalır. Hiçbir şey yapmazsan da adresin doğrulanmamış kalır.",
    ], url, "E-postamı doğrula")


def queue_google_link(session: Session, user: User, google_sub: str) -> EmailOutbox:
    url = _link(issue(session, user, "google_link", google_sub=google_sub))
    return _queue(session, user, "google_link", "Yomiba: Google hesabını bağla", [
        "Yomiba hesabına Google ile girmek istedin. Google hesabını bu hesaba bağlamak için bağlantıya tıkla.",
        f"Bağlantı {GOOGLE_LINK_HOURS} saat geçerli.",
        "Bu isteği sen yapmadıysan bu e-postayı yok say; hesabında hiçbir şey değişmez.",
    ], url, "Google hesabımı bağla")


def send_now(bind: Engine, ids: list[int]) -> None:
    """Background task: send these queued mails now (no-op without SMTP)."""
    from .mailer import send_pending

    session = Session(bind=bind)
    try:
        send_pending(session, ids=ids)
    except Exception:  # noqa: BLE001 - stays queued; the regular sender retries
        logger.exception("account mail: immediate send failed")
        session.rollback()
    finally:
        session.close()
