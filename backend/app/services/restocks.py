""""Tekrar stokta": volumes that are buyable again after selling out.

After every price refresh of a series (background_import), :func:`process`
looks at the series' volumes:

* A volume is in stock when at least one store has it fresh, in stock and
  priced: the same rule as the volume page and the price alerts.
* ``Volume.stock_checked_at`` / ``Volume.last_in_stock_at`` remember the
  last check and the last check that found stock. A volume that was out at
  the previous check, and has had no stock for at least
  ``restock_min_gap_days`` (7), is back in stock: a ``RestockEvent`` is
  written. Shorter gaps are mostly flapping (a store hiding a product for a
  day), so they write nothing. The first check of a volume only records
  its state.
* A volume never seen in stock before counts only when it came out at least
  ``NEW_RELEASE_DAYS`` ago and was listed sold out for the whole gap (an
  out-of-print volume reprinted). A recent one is a new release.

The same pass fires stock alerts ("stoğa girince haber ver") as soon as any
store has the volume (no gap rule: the reader asked for it), and mails
readers who have a restocked volume on their wishlist and do not own it
(``User.restock_mail``, verified addresses only). One mail per reader per
pass, listing every volume.

:func:`recent` serves the home shelf, /tekrar-stokta and the Instagram
draft; :func:`latest_events` the badges on series and volume pages.
"""

from __future__ import annotations

import logging
from collections import defaultdict
from datetime import date, datetime, timedelta, timezone
from html import escape
from zoneinfo import ZoneInfo

from sqlalchemy import func, select
from sqlalchemy.orm import Session, joinedload

from ..config import get_settings
from ..models import (
    CatalogSeries,
    EmailOutbox,
    PriceHistory,
    Publisher,
    RestockEvent,
    Series,
    StockAlert,
    StoreListing,
    User,
    UserVolumeCollection,
    Volume,
    WishlistItem,
)
from ..normalization.volume import UNNUMBERED_VOLUME
from ..utils import from_cents, utcnow
from . import series_slugs
from .catalog_service import stale_listing_ids
from .covers import cover_url
from .price_alert_checker import store_link

logger = logging.getLogger("yomiba.restocks")

#: A volume in stock for the first time that came out this recently is a
#: new release ("Yeni çıkanlar"), not a restock.
NEW_RELEASE_DAYS = 30
#: How long the "Tekrar stokta" badge stays on series and volume pages.
BADGE_DAYS = 14
#: Longest window the public list covers.
MAX_DAYS = 60

TIME_ZONE = ZoneInfo("Europe/Istanbul")


def _aware(value: datetime | None) -> datetime | None:
    if value is None:
        return None
    return value if value.tzinfo else value.replace(tzinfo=timezone.utc)


def min_gap() -> timedelta:
    return timedelta(days=max(1, get_settings().restock_min_gap_days))


def best_offers(session: Session, volume_ids) -> dict[int, StoreListing]:
    """volume id -> cheapest fresh, in-stock, priced listing (what a visitor
    sees as the best price). Volumes without one are left out."""
    ids = list(set(volume_ids))
    if not ids:
        return {}
    listings = list(session.scalars(
        select(StoreListing).options(joinedload(StoreListing.store))
        .where(StoreListing.volume_id.in_(ids), StoreListing.in_stock.is_(True),
               StoreListing.price.is_not(None))
    ))
    stale = stale_listing_ids(session, listings)
    best: dict[int, StoreListing] = {}
    for listing in listings:
        if listing.id in stale:
            continue
        current = best.get(listing.volume_id)
        key = (listing.price, listing.store.name if listing.store else "")
        if current is None or key < (current.price, current.store.name if current.store else ""):
            best[listing.volume_id] = listing
    return best


def _in_stock_counts(session: Session, volume_ids) -> dict[int, int]:
    ids = list(set(volume_ids))
    if not ids:
        return {}
    listings = list(session.scalars(
        select(StoreListing).where(StoreListing.volume_id.in_(ids), StoreListing.in_stock.is_(True),
                                   StoreListing.price.is_not(None))
    ))
    stale = stale_listing_ids(session, listings)
    counts: dict[int, int] = defaultdict(int)
    for listing in listings:
        if listing.id not in stale:
            counts[listing.volume_id] += 1
    return counts


def _today(now: datetime) -> date:
    return now.astimezone(TIME_ZONE).date()


def _first_seen(session: Session, volume_id: int) -> datetime | None:
    """When a store first showed the volume (its first price point)."""
    return _aware(session.scalar(
        select(func.min(PriceHistory.checked_at))
        .join(StoreListing, StoreListing.id == PriceHistory.listing_id)
        .where(StoreListing.volume_id == volume_id)
    ))


def _gap_start(session: Session, volume: Volume, now: datetime) -> datetime | None:
    """Start of the sold-out spell that ends now, or None when it does not
    qualify as a restock (a new release, or nothing known)."""
    if volume.volume_number < 0 or volume.catalog_present is False or volume.catalog_released is False:
        return None
    if volume.last_in_stock_at is not None:
        return _aware(volume.last_in_stock_at)
    # Never seen in stock: an old volume sold out since we know it (reprint),
    # never a recent release coming out.
    if volume.release_date is None or volume.release_date > _today(now) - timedelta(days=NEW_RELEASE_DAYS):
        return None
    return _first_seen(session, volume.id)


def process(session: Session, volume_ids, now: datetime | None = None) -> dict[str, int]:
    """Update the stock state of ``volume_ids``, write restock events, fire
    stock alerts and queue the mails; commits. Returns counts."""
    now = _aware(now) or utcnow()
    ids = sorted(set(volume_ids))
    counts = {"restocked": 0, "alerts": 0, "mails": 0}
    if not ids:
        return counts
    offers = best_offers(session, ids)
    gap = min_gap()
    restocked: list[int] = []
    for volume in session.scalars(select(Volume).where(Volume.id.in_(ids))):
        checked = _aware(volume.stock_checked_at)
        last = _aware(volume.last_in_stock_at)
        was_out = checked is not None and (last is None or last < checked)
        volume.stock_checked_at = now
        offer = offers.get(volume.id)
        if offer is None:
            continue
        if was_out:
            start = _gap_start(session, volume, now)
            if start is not None and now - start >= gap:
                session.add(RestockEvent(volume_id=volume.id, created_at=now, out_since=last,
                                         store_id=offer.store_id, price=offer.price))
                restocked.append(volume.id)
                logger.info("restocks: volume %s back in stock at %s after %s",
                            volume.id, offer.store_id, now - start)
        volume.last_in_stock_at = now
    counts["restocked"] = len(restocked)

    # user id -> volume id -> why ("alert" wins over "wishlist").
    notify: dict[int, dict[int, str]] = defaultdict(dict)
    for alert in session.scalars(select(StockAlert).where(
            StockAlert.volume_id.in_(ids), StockAlert.triggered_at.is_(None))):
        if alert.volume_id in offers:
            alert.triggered_at = now
            notify[alert.user_id][alert.volume_id] = "alert"
            counts["alerts"] += 1
    if restocked:
        owned = set(session.execute(
            select(UserVolumeCollection.user_id, UserVolumeCollection.volume_id)
            .where(UserVolumeCollection.volume_id.in_(restocked), UserVolumeCollection.status == "owned")
        ).all())
        for user_id, volume_id in session.execute(
                select(WishlistItem.user_id, WishlistItem.volume_id).where(WishlistItem.volume_id.in_(restocked))):
            if (user_id, volume_id) not in owned:
                notify[user_id].setdefault(volume_id, "wishlist")

    if notify:
        users = {u.id: u for u in session.scalars(select(User).where(User.id.in_(list(notify))))}
        for user_id, items in notify.items():
            user = users.get(user_id)
            if user is None or not user.is_active:
                continue
            if not (user.restock_mail and user.email_verified_at is not None):
                items = {vid: why for vid, why in items.items() if why == "alert"}
            if items:
                _queue_mail(session, user, items, offers, now)
                counts["mails"] += 1
    session.commit()
    return counts


# -- mail ---------------------------------------------------------------------


def _tl(cents: int) -> str:
    value = from_cents(cents) or 0
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return text.removesuffix(",00") + " TL"


def _volume_label(volume: Volume) -> str:
    return "Numarasız cilt" if volume.volume_number == UNNUMBERED_VOLUME else f"Cilt {volume.volume_number}"


def _volume_path(slug: str, volume: Volume) -> str:
    segment = "cilt-numarasiz" if volume.volume_number == UNNUMBERED_VOLUME else f"cilt-{volume.volume_number}"
    return f"/series/{slug}/{segment}"


def _queue_mail(session: Session, user: User, items: dict[int, str], offers: dict[int, StoreListing],
                now: datetime) -> None:
    site = get_settings().site_url.rstrip("/")
    volumes = list(session.scalars(
        select(Volume).options(joinedload(Volume.series)).where(Volume.id.in_(list(items)))
        .order_by(Volume.series_id, Volume.volume_number)))
    slugs = series_slugs.slugs_for(session, {v.series_id for v in volumes})
    rows = []
    for volume in volumes:
        offer = offers[volume.id]
        rows.append(dict(
            title=f"{volume.series.title} · {_volume_label(volume)}",
            store=offer.store.name if offer.store else "Bir mağaza",
            price=_tl(offer.price), store_url=store_link(offer.product_url),
            page=f"{site}{_volume_path(slugs[volume.series_id], volume)}",
        ))
    if not rows:
        return
    reasons = set(items.values())
    if len(rows) == 1:
        subject = f"Stokta: {rows[0]['title']}"
        lead = f"{rows[0]['title']} yeniden satışta."
    else:
        subject = f"Stokta: {rows[0]['title']} ve {len(rows) - 1} cilt daha"
        lead = f"Beklediğin {len(rows)} cilt yeniden satışta."
    notes = []
    if "alert" in reasons:
        notes.append("Stok alarmı bir kez çalar. Yine haber almak istersen cilt sayfasından yeniden kurabilirsin.")
    if "wishlist" in reasons:
        notes.append("İstek listendeki ciltler tükendikten sonra yeniden satışa çıkınca yazıyoruz. "
                     f"Bu e-postaları Hesabım sayfasından kapatabilirsin: {site}/hesap")

    text = "\n".join([
        f"Merhaba {user.display_name},", "", lead, "",
        *[f"{r['title']}: {r['store']}, {r['price']}\nMağazaya git: {r['store_url']}\n"
          f"Cildin bütün fiyatları: {r['page']}\n" for r in rows],
        *notes, "", "Yomiba",
    ])
    html = "".join([
        f"<p>Merhaba {escape(user.display_name)},</p><p>{escape(lead)}</p><ul>",
        *[f"<li><strong>{escape(r['title'])}</strong>: {escape(r['store'])}, {escape(r['price'])}<br>"
          f'<a href="{escape(r["store_url"])}">Mağazaya git</a> · '
          f'<a href="{escape(r["page"])}">Cildin bütün fiyatları</a></li>' for r in rows],
        "</ul>", *[f"<p>{escape(n)}</p>" for n in notes], "<p>Yomiba</p>",
    ])
    session.add(EmailOutbox(to_email=user.email, subject=subject[:300], body_text=text, body_html=html,
                            kind="restock", ref=f"restock:{user.id}:{now.isoformat()}",
                            created_at=now, next_attempt_at=now))


# -- public lists ---------------------------------------------------------------


def out_days(event: RestockEvent) -> int | None:
    """Whole days the volume was sold out before ``event``; None when it was
    never seen in stock before."""
    if event.out_since is None:
        return None
    return (_aware(event.created_at) - _aware(event.out_since)).days


def latest_events(session: Session, volume_ids, *, days: int = BADGE_DAYS,
                  now: datetime | None = None) -> dict[int, RestockEvent]:
    """volume id -> its newest restock event of the last ``days`` days."""
    ids = list(set(volume_ids))
    if not ids:
        return {}
    since = (_aware(now) or utcnow()) - timedelta(days=days)
    out: dict[int, RestockEvent] = {}
    for event in session.scalars(
            select(RestockEvent).where(RestockEvent.volume_id.in_(ids), RestockEvent.created_at >= since)
            .order_by(RestockEvent.created_at.desc(), RestockEvent.id.desc())):
        out.setdefault(event.volume_id, event)
    return out


def recent(session: Session, *, days: int = 7, now: datetime | None = None) -> list[dict]:
    """Catalog volumes back in stock in the last ``days`` days that are still
    in stock, newest first; each volume once (its latest event)."""
    now = _aware(now) or utcnow()
    since = now - timedelta(days=min(max(1, days), MAX_DAYS))
    latest: dict[int, RestockEvent] = {}
    for event in session.scalars(
            select(RestockEvent).where(RestockEvent.created_at >= since)
            .order_by(RestockEvent.created_at.desc(), RestockEvent.id.desc())):
        latest.setdefault(event.volume_id, event)
    if not latest:
        return []
    offers = best_offers(session, latest)
    ids = [vid for vid in latest if vid in offers]
    if not ids:
        return []
    rows = session.execute(
        select(Volume, Series, Publisher.name)
        .join(Series, Series.id == Volume.series_id)
        .join(Publisher, Publisher.id == Series.publisher_id)
        .where(Volume.id.in_(ids), Series.id.in_(select(CatalogSeries.series_id)),
               Volume.volume_number >= 0, Volume.catalog_present.is_not(False))
    ).all()
    slugs = series_slugs.slugs_for(session, {s.id for _, s, _ in rows})
    stock = _in_stock_counts(session, [v.id for v, _, _ in rows])
    items = []
    for volume, series, publisher in rows:
        event = latest[volume.id]
        offer = offers[volume.id]
        restocked_at = _aware(event.created_at)
        out_since = _aware(event.out_since)
        items.append({
            "volume_id": volume.id, "series_id": series.id, "series_slug": slugs[series.id],
            "series_title": series.title, "publisher": publisher, "author": series.author,
            "volume_number": volume.volume_number,
            "covers_from": volume.covers_from, "covers_to": volume.covers_to,
            "cover_url": cover_url(volume.cover_key),
            "release_date": volume.release_date.isoformat() if volume.release_date else None,
            "restocked_at": restocked_at.isoformat(),
            "out_since": out_since.isoformat() if out_since else None,
            # Days without stock; None when it was never seen in stock before.
            "out_days": out_days(event),
            "price": from_cents(offer.price), "store_name": offer.store.name if offer.store else None,
            "in_stock_count": stock.get(volume.id, 0),
        })
    items.sort(key=lambda i: (i["restocked_at"], i["volume_id"]), reverse=True)
    return items
