"""First-party analytics: record browser events and build the admin report.

Recording (``record``) is called by the public ``POST /olay`` beacon. It drops
bots, admins and floods, turns the request into an anonymous daily visitor
hash, resolves the page to a series / volume and an outbound click to the
store listing behind it. Nothing here may fail a page: the route swallows
errors.

The report (``build_report``) answers everything the admin analytics page
shows for one period, with the previous period of the same length for
comparison. Days and hours are Turkish local time (UTC+3, no DST).
"""

from __future__ import annotations

import hashlib
import logging
import re
import secrets
import threading
import time
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta, timezone
from urllib.parse import parse_qsl, unquote, urlencode, urlsplit, urlunsplit

from sqlalchemy import case, delete, distinct, func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..models import (
    AnalyticsEvent,
    AnalyticsSalt,
    PriceAlert,
    Series,
    Store,
    StoreListing,
    User,
    UserVolumeCollection,
    Volume,
    WishlistItem,
)
from ..normalization.volume import UNNUMBERED_VOLUME
from ..utils import utcnow
from . import series_slugs

logger = logging.getLogger("yomiba.analytics")

TR = timezone(timedelta(hours=3))
KINDS = ("pageview", "outbound", "search", "engage")
#: Raw events are kept this long (13 months: a year-over-year look).
RETENTION_DAYS = 400
#: Events per IP per minute before the beacon stops recording.
RATE_LIMIT = 120
MAX_ENGAGE_SECONDS = 30 * 60

_BOT = re.compile(
    r"bot|crawl|spider|slurp|headless|lighthouse|pingdom|uptime|monitor|preview|scanner|"
    r"facebookexternalhit|whatsapp|telegram|discord|python|curl|wget|httpx|go-http|java/|okhttp",
    re.IGNORECASE,
)


# ---------------------------------------------------------------- recording


def local_now(now: datetime | None = None) -> datetime:
    return (now or utcnow()).astimezone(TR)


def parse_user_agent(ua: str) -> tuple[str, str, str]:
    """(device, browser, os) from a User-Agent; device may be refined by the
    viewport width the browser reports."""
    if re.search(r"iPad|Tablet|Nexus (7|9|10)|SM-T\d", ua) or ("Android" in ua and "Mobile" not in ua):
        device = "tablet"
    elif re.search(r"Mobi|iPhone|iPod|Android", ua):
        device = "mobile"
    else:
        device = "desktop"
    for pattern, name in (
        (r"Edg(A|iOS)?/", "Edge"), (r"OPR/|Opera", "Opera"), (r"SamsungBrowser", "Samsung"),
        (r"YaBrowser", "Yandex"), (r"Firefox|FxiOS", "Firefox"), (r"CriOS|Chrome|Chromium", "Chrome"),
        (r"Safari", "Safari"),
    ):
        if re.search(pattern, ua):
            browser = name
            break
    else:
        browser = "Diğer"
    for pattern, name in (
        (r"Windows", "Windows"), (r"Android", "Android"), (r"iPhone|iPad|iPod|iOS", "iOS"),
        (r"Mac OS X|Macintosh", "macOS"), (r"CrOS", "ChromeOS"), (r"Linux", "Linux"),
    ):
        if re.search(pattern, ua):
            os_name = name
            break
    else:
        os_name = "Diğer"
    return device, browser, os_name


def device_for_width(width: int | None, fallback: str) -> str:
    if not width or width <= 0:
        return fallback
    return "mobile" if width < 640 else "tablet" if width < 1024 else "desktop"


def is_bot(ua: str) -> bool:
    return not ua or bool(_BOT.search(ua))


def client_ip(headers, fallback: str | None) -> str:
    """Cloudflare's header first (DNS is on Cloudflare), then the first
    X-Forwarded-For hop Caddy wrote, then the socket."""
    ip = headers.get("cf-connecting-ip")
    if not ip:
        forwarded = headers.get("x-forwarded-for", "")
        ip = forwarded.split(",")[0].strip()
    return ip or fallback or "0.0.0.0"


def strip_utm(url: str) -> str:
    """The address without our utm_* tags (and without a ``?`` left empty)."""
    parts = urlsplit(url)
    query = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=True) if not k.lower().startswith("utm_")]
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(query) if query else "", parts.fragment))


def host_of(url: str | None) -> str | None:
    if not url:
        return None
    try:
        host = (urlsplit(url).hostname or "").lower()
    except ValueError:
        return None
    if not host:
        # android-app://com.google.android.gm and the like
        return url.split("://", 1)[-1].split("/", 1)[0][:200] or None
    return host.removeprefix("www.")[:200]


_salt_lock = threading.Lock()
_salt_cache: dict[str, str] = {}


def daily_salt(session: Session, day: str) -> str:
    """Today's random salt; older salts are deleted so old hashes can never
    be recomputed. Kept in the database so a restart keeps the same visitor
    counted once."""
    with _salt_lock:
        if day in _salt_cache:
            return _salt_cache[day]
        row = session.get(AnalyticsSalt, day)
        if row is None:
            session.execute(delete(AnalyticsSalt).where(AnalyticsSalt.day < day))
            row = AnalyticsSalt(day=day, salt=secrets.token_hex(32))
            session.add(row)
            try:
                session.commit()
            except IntegrityError:
                session.rollback()
                row = session.get(AnalyticsSalt, day)
        _salt_cache.clear()
        _salt_cache[day] = row.salt
        return row.salt


class RateLimiter:
    def __init__(self, limit: int = RATE_LIMIT, window: float = 60.0):
        self.limit, self.window = limit, window
        self._hits: dict[str, tuple[float, int]] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            if len(self._hits) > 10_000:
                self._hits = {k: v for k, v in self._hits.items() if now - v[0] < self.window}
            start, count = self._hits.get(key, (now, 0))
            if now - start >= self.window:
                start, count = now, 0
            self._hits[key] = (start, count + 1)
            return count < self.limit


_limiter = RateLimiter()
_last_prune: list[str] = [""]


def resolve_page(session: Session, path: str) -> tuple[int | None, int | None]:
    """(series_id, volume_id) for a catalog page path, else (None, None)."""
    parts = [unquote(p) for p in path.split("?", 1)[0].split("/") if p]
    try:
        if len(parts) == 2 and parts[0] == "volume" and parts[1].isdigit():
            volume = session.get(Volume, int(parts[1]))
            return (volume.series_id, volume.id) if volume else (None, None)
        if len(parts) in (2, 3) and parts[0] == "series":
            series_id = series_slugs.series_id_for(session, parts[1])
            if series_id is None or len(parts) == 2:
                return series_id, None
            segment = parts[2]
            if segment == "cilt-numarasiz":
                number = UNNUMBERED_VOLUME
            else:
                m = re.fullmatch(r"cilt-(\d{1,4})", segment)
                if not m:
                    return series_id, None
                number = int(m.group(1))
            volume_id = session.scalar(select(Volume.id).where(
                Volume.series_id == series_id, Volume.volume_number == number))
            return series_id, volume_id
    except Exception:  # never let attribution fail the beacon
        logger.exception("analytics: page resolution failed for %r", path)
    return None, None


def resolve_listing(session: Session, href: str, volume_id: int | None) -> tuple[int | None, int | None, int | None]:
    """(listing_id, store_id, volume_id) behind a clicked store link."""
    candidates = list(dict.fromkeys([href, strip_utm(href), strip_utm(href).split("#", 1)[0]]))
    query = select(StoreListing.id, StoreListing.store_id, StoreListing.volume_id).where(
        StoreListing.product_url.in_(candidates))
    row = None
    if volume_id is not None:
        row = session.execute(query.where(StoreListing.volume_id == volume_id).limit(1)).first()
    if row is None:
        row = session.execute(query.limit(1)).first()
    if row is not None:
        return row[0], row[1], row[2]
    # Not a known listing (store home page, a search link): the store by host.
    parts = urlsplit(href)
    if parts.scheme in ("http", "https") and parts.netloc:
        store_id = session.scalar(select(StoreListing.store_id).where(
            StoreListing.product_url.like(f"{parts.scheme}://{parts.netloc}/%")).limit(1))
        return None, store_id, None
    return None, None, None


def _clean(text: object, limit: int) -> str | None:
    if not isinstance(text, str):
        return None
    text = " ".join(text.split())
    return text[:limit] or None


def record(session: Session, payload: dict, *, headers, client_host: str | None,
           logged_in: bool, now: datetime | None = None) -> bool:
    """Store one beacon event. Returns False when it was dropped."""
    kind = payload.get("k")
    if kind not in KINDS:
        return False
    ua = headers.get("user-agent", "")
    if is_bot(ua):
        return False
    ip = client_ip(headers, client_host)
    if not _limiter.allow(ip):
        return False
    session_id = _clean(payload.get("s"), 32)
    if not session_id or not re.fullmatch(r"[A-Za-z0-9_-]{8,32}", session_id):
        return False

    stamp = now or utcnow()
    local = local_now(stamp)
    day = local.date().isoformat()

    raw_url = _clean(payload.get("u"), 1000) or "/"
    if not raw_url.startswith("/"):
        raw_url = "/"
    parts = urlsplit(raw_url)
    path = (parts.path or "/")[:500]
    params = {k.lower(): v for k, v in parse_qsl(parts.query)}

    device, browser, os_name = parse_user_agent(ua)
    width = payload.get("w")
    device = device_for_width(width if isinstance(width, int) else None, device)
    country = (headers.get("cf-ipcountry") or "").upper()[:2] or None
    if country in ("XX", "T1"):
        country = None

    referrer = _clean(payload.get("r"), 1000)
    referrer_host = host_of(referrer)
    own_host = host_of(headers.get("origin")) or host_of("https://" + headers.get("host", ""))
    if referrer_host and own_host and referrer_host == own_host:
        referrer_host = None

    event = AnalyticsEvent(
        ts=stamp, day=day, hour=local.hour, kind=kind, path=path,
        visitor=hashlib.sha256(f"{daily_salt(session, day)}|{ip}|{ua}".encode()).hexdigest()[:16],
        session=session_id, is_returning=bool(payload.get("n")), logged_in=logged_in,
        referrer_host=referrer_host,
        utm_source=_clean(params.get("utm_source"), 100), utm_medium=_clean(params.get("utm_medium"), 100),
        utm_campaign=_clean(params.get("utm_campaign"), 100),
        device=device, browser=browser, os=os_name, country=country,
    )
    event.series_id, event.volume_id = resolve_page(session, path)

    if kind == "outbound":
        target = _clean(payload.get("t"), 2000)
        if not target or not target.startswith(("http://", "https://")):
            return False
        event.target_url = strip_utm(target)
        event.listing_id, event.store_id, listing_volume = resolve_listing(session, target, event.volume_id)
        if listing_volume is not None and listing_volume != event.volume_id:
            event.volume_id = listing_volume
            event.series_id = session.scalar(select(Volume.series_id).where(Volume.id == listing_volume))
    elif kind == "search":
        query = _clean(payload.get("q"), 200)
        if not query:
            return False
        event.query = query.lower()
        value = payload.get("v")
        event.value = value if isinstance(value, int) and value >= 0 else None
    elif kind == "engage":
        value = payload.get("v")
        if not isinstance(value, int) or value < 1:
            return False
        event.value = min(value, MAX_ENGAGE_SECONDS)

    session.add(event)
    session.commit()
    _prune(session, local.date())
    return True


def _prune(session: Session, today: date) -> None:
    """Once a day, drop events past the retention window."""
    key = today.isoformat()
    if _last_prune[0] == key:
        return
    _last_prune[0] = key
    cutoff = (today - timedelta(days=RETENTION_DAYS)).isoformat()
    deleted = session.execute(delete(AnalyticsEvent).where(AnalyticsEvent.day < cutoff)).rowcount
    session.commit()
    if deleted:
        logger.info("analytics: pruned %d events older than %s", deleted, cutoff)


# ------------------------------------------------------------------ report

E = AnalyticsEvent
PERIODS = (1, 7, 30, 90, 365)


def _days(start: date, end: date) -> list[str]:
    return [(start + timedelta(days=i)).isoformat() for i in range((end - start).days + 1)]


def _in(start: date, end: date):
    return E.day.between(start.isoformat(), end.isoformat())


def _utc_bounds(start: date, end: date) -> tuple[datetime, datetime]:
    lo = datetime.combine(start, datetime.min.time(), TR).astimezone(timezone.utc)
    hi = datetime.combine(end + timedelta(days=1), datetime.min.time(), TR).astimezone(timezone.utc)
    return lo, hi


def _count_if(condition, value=1):
    return func.sum(case((condition, value), else_=0))


def _session_rows(session: Session, start: date, end: date) -> list:
    """Per session that viewed a page: (session, pageviews, outbound clicks,
    searches, engaged seconds, viewed a volume page)."""
    rows = session.execute(
        select(
            E.session,
            _count_if(E.kind == "pageview"),
            _count_if(E.kind == "outbound"),
            _count_if(E.kind == "search"),
            _count_if(E.kind == "engage", func.coalesce(E.value, 0)),
            _count_if((E.kind == "pageview") & E.volume_id.is_not(None)),
        ).where(_in(start, end)).group_by(E.session)
    ).all()
    return [r for r in rows if (r[1] or 0) > 0]


def _totals(session: Session, start: date, end: date) -> dict:
    def scalar(expr, *where):
        return session.scalar(select(expr).where(_in(start, end), *where)) or 0

    pageviews = scalar(func.count(E.id), E.kind == "pageview")
    visitors = scalar(func.count(distinct(E.visitor)), E.kind == "pageview")
    returning = scalar(func.count(distinct(E.visitor)), E.kind == "pageview", E.is_returning.is_(True))
    sessions = _session_rows(session, start, end)
    n = len(sessions)
    bounces = sum(1 for r in sessions if r[1] == 1 and not r[2])
    engaged = sum(r[4] or 0 for r in sessions)
    outbound = scalar(func.count(E.id), E.kind == "outbound")
    clicked = sum(1 for r in sessions if r[2])
    searches = scalar(func.count(E.id), E.kind == "search")
    return dict(
        visitors=visitors,
        returning_visitors=returning,
        sessions=n,
        pageviews=pageviews,
        pages_per_session=round(pageviews / n, 2) if n else 0,
        bounce_rate=round(bounces / n, 4) if n else 0,
        avg_session_seconds=round(engaged / n) if n else 0,
        outbound=outbound,
        outbound_sessions=clicked,
        click_rate=round(clicked / n, 4) if n else 0,
        searches=searches,
        zero_result_searches=scalar(func.count(E.id), E.kind == "search", E.value == 0),
        logged_in_sessions=scalar(func.count(distinct(E.session)), E.logged_in.is_(True)),
    )


def _account_totals(session: Session, start: date, end: date) -> dict:
    lo, hi = _utc_bounds(start, end)

    def created(model):
        return session.scalar(select(func.count()).select_from(model).where(
            model.created_at >= lo, model.created_at < hi)) or 0

    return dict(
        new_users=created(User),
        wishlist_adds=created(WishlistItem),
        price_alerts=created(PriceAlert),
        collection_adds=created(UserVolumeCollection),
    )


def _top(rows, keys, limit):
    return [dict(zip(keys, r)) for r in rows][:limit]


def _volume_labels(session: Session, volume_ids) -> dict[int, dict]:
    ids = [v for v in set(volume_ids) if v is not None]
    if not ids:
        return {}
    rows = session.execute(
        select(Volume.id, Volume.volume_number, Series.id, Series.title)
        .join(Series, Series.id == Volume.series_id).where(Volume.id.in_(ids))
    ).all()
    slugs = series_slugs.slugs_for(session, [r[2] for r in rows])
    out = {}
    for vid, number, sid, title in rows:
        segment = "cilt-numarasiz" if number == UNNUMBERED_VOLUME else f"cilt-{number}"
        out[vid] = dict(
            series=title, number=None if number == UNNUMBERED_VOLUME else number,
            path=f"/series/{slugs[sid]}/{segment}",
        )
    return out


def _series_labels(session: Session, series_ids) -> dict[int, dict]:
    ids = [s for s in set(series_ids) if s is not None]
    if not ids:
        return {}
    titles = dict(session.execute(select(Series.id, Series.title).where(Series.id.in_(ids))).all())
    slugs = series_slugs.slugs_for(session, ids)
    return {sid: dict(title=titles.get(sid), path=f"/series/{slugs[sid]}") for sid in ids if sid in titles}


def _breakdown(session: Session, start: date, end: date, column, limit: int = 12) -> list[dict]:
    """Sessions per value of ``column`` on each session's first page view."""
    first = (select(func.min(E.id)).where(_in(start, end), E.kind == "pageview")
             .group_by(E.session)).scalar_subquery()
    rows = session.execute(
        select(column, func.count()).where(E.id.in_(first)).group_by(column).order_by(func.count().desc())
    ).all()
    return [dict(name=name, sessions=count) for name, count in rows[:limit]]


def build_report(session: Session, days: int = 30, now: datetime | None = None) -> dict:
    if days not in PERIODS:
        days = 30
    stamp = now or utcnow()
    today = local_now(stamp).date()
    start = today - timedelta(days=days - 1)
    prev_end = start - timedelta(days=1)
    prev_start = prev_end - timedelta(days=days - 1)
    period = _in(start, today)

    totals = _totals(session, start, today) | _account_totals(session, start, today)
    previous = _totals(session, prev_start, prev_end) | _account_totals(session, prev_start, prev_end)

    # Time series: hours for a single day, days otherwise.
    bucket = E.hour if days == 1 else E.day
    rows = session.execute(
        select(bucket, E.kind, func.count(), func.count(distinct(E.visitor)))
        .where(period, E.kind.in_(("pageview", "outbound", "search"))).group_by(bucket, E.kind)
    ).all()
    keys = list(range(24)) if days == 1 else _days(start, today)
    series = {k: dict(t=k, pageviews=0, visitors=0, outbound=0, searches=0) for k in keys}
    for key, kind, count, visitors in rows:
        point = series.get(key)
        if point is None:
            continue
        if kind == "pageview":
            point["pageviews"], point["visitors"] = count, visitors
        elif kind == "outbound":
            point["outbound"] = count
        else:
            point["searches"] = count

    # Right now: anyone active in the last five minutes.
    recent = stamp - timedelta(minutes=5)
    live_rows = session.execute(
        select(E.path, func.count(distinct(E.session))).where(E.ts >= recent, E.kind == "pageview")
        .group_by(E.path).order_by(func.count(distinct(E.session)).desc()).limit(5)
    ).all()
    live = dict(
        sessions=session.scalar(select(func.count(distinct(E.session))).where(E.ts >= recent)) or 0,
        pages=[dict(path=p, sessions=c) for p, c in live_rows],
    )

    # Pages.
    engaged = dict(session.execute(
        select(E.path, func.avg(E.value)).where(period, E.kind == "engage").group_by(E.path)).all())
    page_rows = session.execute(
        select(E.path, func.count(), func.count(distinct(E.visitor)))
        .where(period, E.kind == "pageview").group_by(E.path).order_by(func.count().desc()).limit(30)
    ).all()
    pages = [dict(path=p, pageviews=c, visitors=v, avg_seconds=round(engaged.get(p) or 0)) for p, c, v in page_rows]

    def edge_pages(fn):
        ids = (select(fn(E.id)).where(period, E.kind == "pageview").group_by(E.session)).scalar_subquery()
        return [dict(path=p, sessions=c) for p, c in session.execute(
            select(E.path, func.count()).where(E.id.in_(ids)).group_by(E.path)
            .order_by(func.count().desc()).limit(10)).all()]

    # Series and volumes: views, store clicks and how often a view ends in one.
    def by(column, kind):
        return {k: (c, v) for k, c, v in session.execute(
            select(column, func.count(), func.count(distinct(E.session)))
            .where(period, E.kind == kind, column.is_not(None)).group_by(column)).all()}

    series_views, series_clicks = by(E.series_id, "pageview"), by(E.series_id, "outbound")
    series_ids = sorted(set(series_views) | set(series_clicks),
                        key=lambda s: (-(series_views.get(s, (0, 0))[0]), -(series_clicks.get(s, (0, 0))[0])))[:30]
    labels = _series_labels(session, series_ids)
    top_series = [dict(
        series_id=s, title=labels.get(s, {}).get("title") or f"#{s}", path=labels.get(s, {}).get("path"),
        pageviews=series_views.get(s, (0, 0))[0], sessions=series_views.get(s, (0, 0))[1],
        outbound=series_clicks.get(s, (0, 0))[0],
    ) for s in series_ids]

    volume_views, volume_clicks = by(E.volume_id, "pageview"), by(E.volume_id, "outbound")
    volume_ids = sorted(set(volume_views) | set(volume_clicks),
                        key=lambda v: (-(volume_views.get(v, (0, 0))[0]), -(volume_clicks.get(v, (0, 0))[0])))[:40]
    vlabels = _volume_labels(session, volume_ids)
    top_volumes = []
    for v in volume_ids:
        views, view_sessions = volume_views.get(v, (0, 0))
        clicks, click_sessions = volume_clicks.get(v, (0, 0))
        label = vlabels.get(v, {})
        top_volumes.append(dict(
            volume_id=v, series=label.get("series") or f"Cilt #{v}", number=label.get("number"),
            path=label.get("path"), pageviews=views, sessions=view_sessions, outbound=clicks,
            click_rate=round(min(click_sessions / view_sessions, 1), 4) if view_sessions else None,
        ))

    # Stores.
    store_names = dict(session.execute(select(Store.id, Store.name)).all())
    store_rows = session.execute(
        select(E.store_id, func.count(), func.count(distinct(E.session)), func.count(distinct(E.volume_id)))
        .where(period, E.kind == "outbound", E.store_id.is_not(None)).group_by(E.store_id)
        .order_by(func.count().desc())
    ).all()
    store_day = defaultdict(Counter)
    for store_id, key, count in session.execute(
        select(E.store_id, bucket, func.count()).where(period, E.kind == "outbound", E.store_id.is_not(None))
        .group_by(E.store_id, bucket)
    ).all():
        store_day[store_id][key] = count
    stores = [dict(
        store_id=s, name=store_names.get(s, f"#{s}"), clicks=c, sessions=sess, volumes=vols,
        trend=[store_day[s].get(k, 0) for k in keys],
    ) for s, c, sess, vols in store_rows]
    unknown_rows = session.execute(
        select(E.target_url).where(period, E.kind == "outbound", E.store_id.is_(None))
    ).scalars().all()
    other_links = [dict(host=h, clicks=c) for h, c in Counter(host_of(u) or "?" for u in unknown_rows).most_common(10)]

    # Searches.
    search_rows = session.execute(
        select(E.query, func.count(), func.avg(E.value), func.max(E.ts))
        .where(period, E.kind == "search").group_by(E.query).order_by(func.count().desc()).limit(30)
    ).all()
    zero_rows = session.execute(
        select(E.query, func.count(), func.max(E.ts))
        .where(period, E.kind == "search", E.value == 0).group_by(E.query)
        .order_by(func.count().desc()).limit(30)
    ).all()
    search_sessions = set(session.scalars(select(E.session).distinct().where(period, E.kind == "search")))
    click_sessions = set(session.scalars(select(E.session).distinct().where(period, E.kind == "outbound")))

    # When people come: weekday x hour page views.
    heat = [[0] * 24 for _ in range(7)]
    for day, hour, count in session.execute(
        select(E.day, E.hour, func.count()).where(period, E.kind == "pageview").group_by(E.day, E.hour)
    ).all():
        heat[date.fromisoformat(day).weekday()][hour] += count

    # Funnel over sessions.
    session_rows = _session_rows(session, start, today)
    funnel = dict(
        sessions=len(session_rows),
        viewed_volume=sum(1 for r in session_rows if r[5]),
        clicked_store=sum(1 for r in session_rows if r[2]),
    )
    depth = Counter(min(r[1], 10) for r in session_rows)

    return dict(
        generated_at=stamp,
        days=days,
        start=start.isoformat(),
        end=today.isoformat(),
        bucket="hour" if days == 1 else "day",
        totals=totals,
        previous=previous,
        series=list(series.values()),
        live=live,
        pages=pages,
        entry_pages=edge_pages(func.min),
        exit_pages=edge_pages(func.max),
        top_series=top_series,
        top_volumes=top_volumes,
        stores=stores,
        other_links=other_links,
        searches=[dict(query=q, count=c, avg_results=round(a, 1) if a is not None else None, last=t)
                  for q, c, a, t in search_rows],
        zero_searches=[dict(query=q, count=c, last=t) for q, c, t in zero_rows],
        search_click_rate=round(len(search_sessions & click_sessions) / len(search_sessions), 4) if search_sessions else None,
        referrers=_breakdown(session, start, today, E.referrer_host),
        utm_sources=_breakdown(session, start, today, E.utm_source),
        utm_campaigns=_breakdown(session, start, today, E.utm_campaign),
        devices=_breakdown(session, start, today, E.device),
        browsers=_breakdown(session, start, today, E.browser),
        systems=_breakdown(session, start, today, E.os),
        countries=_breakdown(session, start, today, E.country),
        heatmap=heat,
        funnel=funnel,
        session_depth=[dict(pages=k, sessions=depth.get(k, 0)) for k in range(1, 11)],
        users_total=session.scalar(select(func.count(User.id))) or 0,
        retention_days=RETENTION_DAYS,
    )
