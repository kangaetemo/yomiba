"""Visitors' "hatalı içerik" reports: the public form's checks and the
admin list.

Anyone may report, signed in or not, because most readers never sign in.
Abuse is kept small instead of locked out:

- per sender (account, else IP) 3 reports per 10 minutes and 10 per day,
  and at most 300 reports a day site-wide; the open (``new``) list never
  grows past 500, so a flood cannot fill the disk;
- a hidden "website" field that people never see (bots fill it), a form
  that was sent within 3 seconds of opening, a crawler user agent, more
  than two links in the text, or the same text from the same sender on the
  same page within a day are all dropped silently: the sender is told
  "thanks" and learns nothing;
- the text is plain text up to 1000 characters; the admin page shows it
  as text, never as HTML or as clickable links.
"""

from __future__ import annotations

import hashlib
import re
import threading
import time
from collections import deque
from datetime import timedelta

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from ..models import ContentReport, Store, User
from ..utils import utcnow
from . import analytics

CATEGORIES = {
    "price": "Fiyat yanlış",
    "stock": "Stok bilgisi yanlış",
    "match": "Yanlış ürün / mağaza eşleşmesi",
    "info": "Cilt bilgisi yanlış (künye, kapak, tarih)",
    "other": "Diğer",
}
STATUSES = ("new", "resolved", "dismissed")
MIN_LENGTH, MAX_LENGTH = 10, 1000
MIN_FILL_MS = 3000
MAX_LINKS = 2
MAX_OPEN = 500

_URL = re.compile(r"https?://|www\.", re.IGNORECASE)
_CONTROL = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_PAGE = re.compile(r"/series/[^/?#\s]{1,200}(/cilt-(\d{1,4}|numarasiz))?")


class SlidingLimiter:
    """At most ``limit`` hits per ``window`` seconds for each key."""

    def __init__(self, limit: int, window: float):
        self.limit, self.window = limit, window
        self._hits: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if key not in self._hits and len(self._hits) >= 10_000:
                self._hits = {k: v for k, v in self._hits.items() if v and now - v[-1] < self.window}
            hits = self._hits.setdefault(key, deque())
            while hits and hits[0] <= now - self.window:
                hits.popleft()
            if len(hits) >= self.limit:
                return False
            hits.append(now)
            return True


_burst = SlidingLimiter(3, 600)
_daily = SlidingLimiter(10, 86_400)
_site = SlidingLimiter(300, 86_400)

TOO_MANY = "Çok fazla bildirim gönderdin. Biraz sonra tekrar dene."
CLOSED = "Şu an bildirim alınamıyor. Daha sonra tekrar dene."


def clean_message(text: object) -> str:
    if not isinstance(text, str):
        return ""
    text = _CONTROL.sub("", text.replace("\r\n", "\n"))
    lines = [" ".join(line.split()) for line in text.split("\n")]
    return re.sub(r"\n{3,}", "\n\n", "\n".join(lines)).strip()


def submit(session: Session, payload: dict, *, headers, client_host: str | None, user: User | None) -> bool:
    """Store one report. Returns False when it was dropped silently; raises
    422/429 for what a real person should be told."""
    message = clean_message(payload.get("message"))
    if len(message) < MIN_LENGTH:
        raise HTTPException(status_code=422, detail=f"Lütfen hatayı en az {MIN_LENGTH} karakterle anlat.")
    if len(message) > MAX_LENGTH:
        raise HTTPException(status_code=422, detail=f"Bildirim en fazla {MAX_LENGTH} karakter olabilir.")
    category = payload.get("category")
    if category not in CATEGORIES:
        category = "other"
    path = payload.get("path")
    match = _PAGE.fullmatch(path) if isinstance(path, str) else None
    if match is None:
        raise HTTPException(status_code=422, detail="Bildirim yalnızca seri ve cilt sayfalarından gönderilebilir.")

    # Bot traps: answered like a success.
    filled_in = payload.get("filled_ms")
    if payload.get("website") or not isinstance(filled_in, int) or filled_in < MIN_FILL_MS:
        return False
    if analytics.is_bot(headers.get("user-agent", "")):
        return False
    if len(_URL.findall(message)) > MAX_LINKS:
        return False

    ip = analytics.client_ip(headers, client_host)
    sender = f"user:{user.id}" if user is not None else f"ip:{ip}"
    if not (_burst.allow(sender) and _daily.allow(sender)):
        raise HTTPException(status_code=429, detail=TOO_MANY)
    if not _site.allow("site"):
        raise HTTPException(status_code=429, detail=CLOSED)
    if session.scalar(select(func.count()).select_from(ContentReport).where(ContentReport.status == "new")) >= MAX_OPEN:
        raise HTTPException(status_code=429, detail=CLOSED)

    now = utcnow()
    day = analytics.local_now(now).date().isoformat()
    reporter = hashlib.sha256(f"{analytics.daily_salt(session, day)}|report|{ip}".encode()).hexdigest()[:16]
    page = match.group(0)
    duplicate = session.scalar(select(ContentReport.id).where(
        ContentReport.reporter == reporter, ContentReport.path == page,
        ContentReport.message == message, ContentReport.created_at >= now - timedelta(days=1),
    ).limit(1))
    if duplicate is not None:
        return False

    series_id, volume_id = analytics.resolve_page(session, page)
    if series_id is None:
        raise HTTPException(status_code=422, detail="Bildirim yalnızca seri ve cilt sayfalarından gönderilebilir.")
    store_id = None
    store = payload.get("store")
    if isinstance(store, str) and store.strip():
        store_id = session.scalar(select(Store.id).where(Store.name == store.strip()[:200]))

    session.add(ContentReport(
        created_at=now, category=category, message=message, path=page,
        series_id=series_id, volume_id=volume_id, store_id=store_id,
        user_id=user.id if user is not None else None, reporter=reporter, status="new",
    ))
    session.commit()
    return True


def _item(report: ContentReport, series: dict, volumes: dict, stores: dict, users: dict) -> dict:
    volume = volumes.get(report.volume_id) if report.volume_id is not None else None
    serie = series.get(report.series_id) if report.series_id is not None else None
    user = users.get(report.user_id) if report.user_id is not None else None
    return dict(
        id=report.id, created_at=report.created_at.isoformat(), status=report.status,
        resolved_at=report.resolved_at.isoformat() if report.resolved_at else None,
        category=report.category, category_label=CATEGORIES.get(report.category, report.category),
        message=report.message,
        # Link to the page as it is now (a renamed series has a new slug).
        path=(volume or serie or {}).get("path") or report.path,
        series=(serie or {}).get("title") or (volume or {}).get("series"),
        volume_number=(volume or {}).get("number"),
        store=stores.get(report.store_id),
        user=dict(id=user[0], name=user[1], email=user[2]) if user else None,
        reporter=report.reporter,
    )


def admin_list(session: Session, status: str | None, limit: int = 200) -> dict:
    query = select(ContentReport).order_by(ContentReport.created_at.desc(), ContentReport.id.desc()).limit(limit)
    if status in STATUSES:
        query = query.where(ContentReport.status == status)
    reports = list(session.scalars(query))
    series = analytics._series_labels(session, [r.series_id for r in reports])
    volumes = analytics._volume_labels(session, [r.volume_id for r in reports])
    store_ids = {r.store_id for r in reports if r.store_id is not None}
    stores = dict(session.execute(select(Store.id, Store.name).where(Store.id.in_(store_ids))).all()) if store_ids else {}
    user_ids = {r.user_id for r in reports if r.user_id is not None}
    users = {row[0]: tuple(row) for row in session.execute(
        select(User.id, User.display_name, User.email).where(User.id.in_(user_ids)))} if user_ids else {}
    counts = dict(session.execute(select(ContentReport.status, func.count()).group_by(ContentReport.status)).all())
    return dict(
        counts={s: counts.get(s, 0) for s in STATUSES},
        items=[_item(r, series, volumes, stores, users) for r in reports],
    )


def open_count(session: Session) -> int:
    return session.scalar(select(func.count()).select_from(ContentReport).where(ContentReport.status == "new")) or 0


def set_status(session: Session, report_id: int, status: str) -> None:
    if status not in STATUSES:
        raise HTTPException(status_code=422, detail="Geçersiz durum.")
    report = session.get(ContentReport, report_id)
    if report is None:
        raise HTTPException(status_code=404, detail="Bildirim bulunamadı.")
    report.status = status
    report.resolved_at = None if status == "new" else utcnow()
    session.commit()
