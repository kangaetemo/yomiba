"""Current market price drops, relative to observed selling prices.

A volume appears once, at its cheapest fresh buyable listing. The reference
is a time-weighted median of market minima in the preceding 30 days (at least
7 days of coverage), or the immediately preceding market minimum when the
history is shorter. Retail list prices never enter this calculation.

Legacy history has no stock evidence: it describes observed selling prices,
not a guarantee that the historical offer was continuously purchasable. New
points retain stock/product context and expire after 48 hours without another
observation. Unknown/expired intervals do not contribute to the reference.
"""
from __future__ import annotations

import threading
import time
from collections import defaultdict
from datetime import datetime, timedelta, timezone

from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, aliased

from ..config import get_settings
from ..models import CatalogSeries, PriceHistory, Series, Store, StoreListing, Volume
from ..utils import from_cents, utcnow
from . import series_slugs
from .covers import cover_url

REFERENCE_DAYS = 30
MIN_REFERENCE_DAYS = 7
HOME_MIN_PERCENT = 10
#: Smaller drops (a 60-kuruş rounding change) are still recorded and kept
#: in the API, but public lists and badges leave them out.
MIN_NOTICEABLE_PERCENT = 5
MIN_NOTICEABLE_SAVING_CENTS = 500
#: The site-wide list (home, /indirimler) is shared by every visitor and
#: takes seconds to compute; prices change on a 4-hour refresh cycle.
CACHE_SECONDS = 300

_cache: dict[tuple, tuple[float, list[dict]]] = {}
_cache_lock = threading.Lock()


def clear_cache() -> None:
    _cache.clear()


def aware(value: datetime) -> datetime:
    return value.replace(tzinfo=timezone.utc) if value.tzinfo is None else value.astimezone(timezone.utc)


def _timeline(listings, histories, start, now):
    """Market price intervals, including known stock changes and expiry."""
    events = defaultdict(list)
    for listing in listings:
        points = histories.get(listing.id, [])
        for point in points:
            if point.product_url is not None and point.product_url != listing.product_url:
                continue
            stamp = aware(point.checked_at)
            if stamp > now or point.price <= 0:
                continue
            if point.in_stock is not None and stamp + timedelta(hours=48) <= start:
                continue
            events[max(start, stamp)].append((listing.id, point.price, point.in_stock, point.id))
            if point.in_stock is not None:
                expiry = stamp + timedelta(hours=48)
                if start < expiry <= now:
                    events[expiry].append((listing.id, None, None, point.id))
    values = {}
    versions = {}
    intervals = []
    times = sorted(events)
    for i, stamp in enumerate(times):
        # Older expiry cannot cancel a newer observation at the same instant.
        for lid, price, stock, version in sorted(events[stamp], key=lambda e: (e[3], e[1] is not None)):
            if price is None:
                if versions.get(lid) == version:
                    values.pop(lid, None)
            else:
                versions[lid] = version
                if stock is False:
                    values.pop(lid, None)
                else:
                    values[lid] = price
        end = times[i + 1] if i + 1 < len(times) else now
        price = min(values.values()) if values else None
        if end > stamp:
            if intervals and intervals[-1][2] == price and intervals[-1][1] == stamp:
                intervals[-1] = (intervals[-1][0], end, price)
            else:
                intervals.append((stamp, end, price))
    return intervals


def _reference(intervals, changed_at):
    weights = defaultdict(float)
    for start, end, price in intervals:
        seconds = (min(end, changed_at) - start).total_seconds()
        if price is not None and seconds > 0:
            weights[price] += seconds
    covered = sum(weights.values())
    if covered < MIN_REFERENCE_DAYS * 86400:
        return None, covered
    accumulated = 0.0
    for price, seconds in sorted(weights.items()):
        accumulated += seconds
        if accumulated >= covered / 2:
            return price, covered
    return None, covered


def current_price_deals(session: Session, *, volume_id: int | None = None, hours=168, now=None):
    """Current deals, newest first. The site-wide list (no volume, no fixed
    ``now``) is cached for CACHE_SECONDS; callers must not mutate it."""
    if volume_id is not None or now is not None:
        return _compute(session, volume_id=volume_id, hours=hours, now=now)
    key = (id(session.get_bind()), hours)
    hit = _cache.get(key)
    if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
        return hit[1]
    # One computation at a time: concurrent first visitors wait for it.
    with _cache_lock:
        hit = _cache.get(key)
        if hit and time.monotonic() - hit[0] < CACHE_SECONDS:
            return hit[1]
        deals = _compute(session, volume_id=None, hours=hours, now=None)
        _cache[key] = (time.monotonic(), deals)
        return deals


def _compute(session: Session, *, volume_id: int | None, hours, now):
    now = aware(now or utcnow())
    start = now - timedelta(days=REFERENCE_DAYS)
    freshness = now - timedelta(hours=max(1, get_settings().listing_stale_hours))
    # Daily unchanged observations need not load a volume's full timeline.
    # Indexed predecessor lookups shortlist real price/stock changes first.
    previous = aliased(PriceHistory)
    previous_price = select(previous.price).where(
        previous.listing_id == PriceHistory.listing_id, previous.id < PriceHistory.id
    ).order_by(previous.id.desc()).limit(1).scalar_subquery()
    previous_stock = select(previous.in_stock).where(
        previous.listing_id == PriceHistory.listing_id, previous.id < PriceHistory.id
    ).order_by(previous.id.desc()).limit(1).scalar_subquery()
    candidates = select(StoreListing.volume_id).join(
        PriceHistory, PriceHistory.listing_id == StoreListing.id
    ).where(PriceHistory.checked_at >= now - timedelta(hours=hours),
            PriceHistory.checked_at <= now, PriceHistory.price > 0,
            or_(previous_price.is_(None), PriceHistory.price < previous_price,
                PriceHistory.in_stock.is_(True) & previous_stock.is_(False)))
    if volume_id is not None:
        # A volume page needs only its own listings' history scanned.
        candidates = candidates.where(StoreListing.volume_id == volume_id)
    query = (
        select(StoreListing, Volume, Series, Store)
        .join(Volume, Volume.id == StoreListing.volume_id)
        .join(Series, Series.id == Volume.series_id)
        .join(Store, Store.id == StoreListing.store_id)
        .where(Volume.id.in_(candidates), Series.id.in_(select(CatalogSeries.series_id)), Volume.volume_number >= 0,
               Volume.catalog_released.is_not(False))
    )
    if volume_id is not None:
        query = query.where(Volume.id == volume_id)
    rows = session.execute(query).all()
    if not rows:
        return []
    listing_ids = [r[0].id for r in rows]
    # Include a predecessor at the start boundary without loading all history.
    before = select(func.max(PriceHistory.id)).where(
        PriceHistory.listing_id.in_(listing_ids), PriceHistory.checked_at < start
    ).group_by(PriceHistory.listing_id)
    points = session.scalars(select(PriceHistory).where(
        PriceHistory.listing_id.in_(listing_ids), PriceHistory.checked_at <= now,
        or_(PriceHistory.checked_at >= start, PriceHistory.id.in_(before))
    ).order_by(PriceHistory.checked_at, PriceHistory.id)).all()
    histories = defaultdict(list)
    for point in points:
        histories[point.listing_id].append(point)
    grouped = defaultdict(list)
    for row in rows:
        grouped[row[1].id].append(row)
    slugs = series_slugs.slugs_for(session, [r[2].id for r in rows])
    deals = []
    for entries in grouped.values():
        buyable = [r for r in entries if r[0].in_stock and r[0].price is not None
                   and r[0].price > 0 and aware(r[0].last_checked) >= freshness]
        if not buyable:
            continue
        buyable.sort(key=lambda r: (r[0].price, r[3].name, r[0].id))
        listing, volume, series, store = buyable[0]
        timeline = _timeline([r[0] for r in entries], histories, start, now)
        if not timeline or timeline[-1][2] != listing.price or len(timeline) < 2:
            continue  # first observation, changed product, or history/current mismatch
        changed_at = timeline[-1][0]
        previous = timeline[-2][2]
        if previous is None or previous <= listing.price or changed_at < now - timedelta(hours=hours):
            continue
        reference, coverage = _reference(timeline, changed_at)
        kind = "usual" if reference is not None else "previous"
        reference = reference if reference is not None else previous
        if reference <= listing.price:
            continue  # returning to an ordinary price after a short-lived rise
        saving = reference - listing.price
        percent = saving * 100 / reference
        noticeable = percent >= MIN_NOTICEABLE_PERCENT and saving >= MIN_NOTICEABLE_SAVING_CENTS
        alternatives = [r[0].price for r in buyable if r[0].id != listing.id and r[0].price > listing.price]
        alternative = min(alternatives) if alternatives else None
        deals.append({
            "listing_id": listing.id, "volume_id": volume.id, "series_id": series.id,
            "series_slug": slugs[series.id], "series_title": series.title,
            "volume_number": volume.volume_number, "store_name": store.name,
            "old_price": from_cents(reference), "new_price": from_cents(listing.price),
            "saving": from_cents(saving), "drop_pct": round(percent, 1),
            "reference_kind": kind, "reference_days": round(coverage / 86400, 1),
            "noticeable": noticeable,
            "significant": noticeable and kind == "usual" and percent >= HOME_MIN_PERCENT,
            "lowest_ever": False,
            "changed_at": changed_at.isoformat(), "in_stock": True,
            "product_url": listing.product_url, "image_url": cover_url(volume.cover_key),
            "alternative_price": from_cents(alternative),
        })
    if deals:
        # Keep the legacy flag's all-time meaning, not just a 30-day low.
        lows = dict(session.execute(
            select(StoreListing.volume_id, func.min(PriceHistory.price))
            .join(PriceHistory, PriceHistory.listing_id == StoreListing.id)
            .where(StoreListing.volume_id.in_([d["volume_id"] for d in deals]),
                   PriceHistory.price > 0, PriceHistory.in_stock.is_not(False),
                   or_(PriceHistory.product_url.is_(None),
                       PriceHistory.product_url == StoreListing.product_url))
            .group_by(StoreListing.volume_id)
        ).all())
        for deal in deals:
            low = lows.get(deal["volume_id"])
            deal["lowest_ever"] = low is not None and round(deal["new_price"] * 100) <= low
    return sorted(deals, key=lambda d: (d["changed_at"], d["volume_id"]), reverse=True)
