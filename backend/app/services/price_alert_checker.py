"""Evaluate price alerts and queue their e-mails.

Run after every price refresh of a series (background_import) for that
series' volumes. The best price is what a visitor sees on the volume page:
the cheapest fresh, in-stock listing (``stale_listing_ids`` excluded).

One mail per crossing: an armed alert (``triggered_at`` is None) whose best
price is at or below the threshold fires — ``triggered_at`` is set and a
mail queued in ``email_outbox`` in the same transaction. It re-arms when an
in-stock best price is seen above the threshold again, and when the user
changes the threshold. No in-stock offer changes nothing: stores that hide
sold-out products would otherwise re-send the same mail.
"""

from __future__ import annotations

import logging
from html import escape
from urllib.parse import parse_qsl, urlsplit, urlunsplit

from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from ..config import get_settings
from ..models import EmailOutbox, PriceAlert, Series, StoreListing, User, Volume
from ..utils import from_cents, utcnow
from .catalog_service import stale_listing_ids
from .series_slugs import slug_for

logger = logging.getLogger("yomiba.alerts")


def best_offer(session: Session, volume_id: int) -> StoreListing | None:
    listings = list(session.scalars(
        select(StoreListing).options(joinedload(StoreListing.store))
        .where(StoreListing.volume_id == volume_id, StoreListing.in_stock.is_(True),
               StoreListing.price.is_not(None))
    ))
    stale = stale_listing_ids(session, listings)
    fresh = [l for l in listings if l.id not in stale]
    return min(fresh, key=lambda l: (l.price, l.store.name if l.store else "")) if fresh else None


def store_link(url: str, medium: str = "email") -> str:
    """Tag an outbound store link so the store sees the visit came from
    Yomiba (same rule as the frontend's ``storeLink``): the store's own query
    string is kept and an existing ``utm_source`` is not overwritten."""
    parts = urlsplit(url)
    if parts.scheme not in ("http", "https"):
        return url
    if any(k == "utm_source" for k, _ in parse_qsl(parts.query, keep_blank_values=True)):
        return url
    tag = f"utm_source=yomiba&utm_medium={medium}"
    # Appended as text: re-encoding the store's own query could change it.
    return urlunsplit(parts._replace(query=f"{parts.query}&{tag}" if parts.query else tag))


def _tl(cents: int) -> str:
    value = from_cents(cents)
    text = f"{value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return text.removesuffix(",00") + " TL"


def _mail(alert: PriceAlert, volume: Volume, user: User, offer: StoreListing, url: str) -> tuple[str, str, str]:
    title = f"{volume.series.title} · Cilt {volume.volume_number}"
    store = offer.store.name if offer.store else "bir mağaza"
    store_url = store_link(offer.product_url)
    subject = f"Fiyat alarmı: {title} {_tl(offer.price)}"
    text = (
        f"Merhaba {user.display_name},\n\n"
        f"{title} için kurduğun fiyat alarmı çaldı: {store} şu an {_tl(offer.price)} "
        f"(alarm fiyatın {_tl(alert.threshold_price)}).\n\n"
        f"Mağazaya git: {store_url}\n"
        f"Cildin bütün fiyatları: {url}\n\n"
        "Fiyat yeniden alarm fiyatının üstüne çıkıp tekrar düşerse yine haber veririz. "
        "Alarmı cilt sayfasından değiştirebilir ya da kapatabilirsin.\n\n"
        "Yomiba"
    )
    html = (
        f"<p>Merhaba {escape(user.display_name)},</p>"
        f"<p><strong>{escape(title)}</strong> için kurduğun fiyat alarmı çaldı: "
        f"{escape(store)} şu an <strong>{escape(_tl(offer.price))}</strong> "
        f"(alarm fiyatın {escape(_tl(alert.threshold_price))}).</p>"
        f'<p><a href="{escape(store_url)}">Mağazaya git</a> · '
        f'<a href="{escape(url)}">Cildin bütün fiyatları</a></p>'
        "<p>Fiyat yeniden alarm fiyatının üstüne çıkıp tekrar düşerse yine haber veririz. "
        "Alarmı cilt sayfasından değiştirebilir ya da kapatabilirsin.</p><p>Yomiba</p>"
    )
    return subject, text, html


def check_alerts(session: Session, volume_ids) -> dict[str, int]:
    """Evaluate the active alerts of ``volume_ids``; commits. Returns counts."""
    ids = list(set(volume_ids))
    counts = {"fired": 0, "rearmed": 0}
    if not ids:
        return counts
    alerts = list(session.scalars(
        select(PriceAlert).where(PriceAlert.volume_id.in_(ids), PriceAlert.is_active.is_(True))))
    if not alerts:
        return counts
    site = get_settings().site_url.rstrip("/")
    best: dict[int, StoreListing | None] = {}
    for alert in alerts:
        if alert.volume_id not in best:
            best[alert.volume_id] = best_offer(session, alert.volume_id)
        offer = best[alert.volume_id]
        if offer is None:
            continue  # no in-stock offer: neither fire nor re-arm (stock flaps)
        if offer.price > alert.threshold_price:
            if alert.triggered_at is not None:
                alert.triggered_at = alert.triggered_price = None
                counts["rearmed"] += 1
            continue
        if alert.triggered_at is not None:
            continue  # already mailed for this crossing
        volume = session.scalar(select(Volume).options(joinedload(Volume.series).joinedload(Series.publisher))
                                .where(Volume.id == alert.volume_id))
        user = session.get(User, alert.user_id)
        if volume is None or user is None or not getattr(user, "is_active", True):
            continue
        now = utcnow()
        alert.triggered_at, alert.triggered_price = now, offer.price
        url = f"{site}/series/{slug_for(session, volume.series_id)}/cilt-{volume.volume_number}"
        subject, text, html = _mail(alert, volume, user, offer, url)
        session.add(EmailOutbox(to_email=user.email, subject=subject, body_text=text, body_html=html,
                                kind="price_alert", ref=f"price_alert:{alert.id}:{now.isoformat()}",
                                created_at=now, next_attempt_at=now))
        counts["fired"] += 1
        logger.info("alerts: alert %s fired for volume %s at %s (threshold %s)",
                    alert.id, alert.volume_id, offer.price, alert.threshold_price)
    session.commit()
    return counts
