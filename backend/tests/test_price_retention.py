"""Amazon prices are kept and shown for at most 24 hours.

Amazon's associate terms forbid storing or showing its pricing for longer
(Yomiba's Amazon Influencer application was rejected over it). Amazon is
not scraped on the server (DISABLED_STORES), so its old listings never
refresh; the store-wide stale rule does not catch them either, because a
store that is down as a whole keeps its listings fresh.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.models import ListingChange, PriceHistory, Store, StoreListing
from app.services import catalog_service
from app.services.price_alert_checker import best_offer
from app.services.price_retention import purge_expired_prices
from app.utils import utcnow
from tests.test_import_service import seed_catalog_series


@pytest.fixture()
def amazon_case(db_session):
    """v1: Amazon 90 TL checked 3 days ago, BKM 150 TL fresh.
    v2: Amazon 80 TL checked 2 hours ago, BKM 150 TL fresh.
    v3: only an Amazon 70 TL listing, checked 3 days ago."""
    now = utcnow()
    series = seed_catalog_series(db_session, "Amazon Kural", "Kural Yayin", volumes=(1, 2, 3))
    v1, v2, v3 = sorted(series.volumes, key=lambda v: v.volume_number)
    amazon, bkm = Store(code="amazon", name="Amazon"), Store(code="bkm", name="BKM Kitap")
    db_session.add_all([amazon, bkm])
    db_session.flush()

    def listing(volume, store, price, hours_ago):
        row = StoreListing(volume_id=volume.id, store_id=store.id, product_url=f"https://x/{volume.id}/{store.id}",
                           price=price, in_stock=True, last_checked=now - timedelta(hours=hours_ago))
        db_session.add(row)
        db_session.flush()
        db_session.add(PriceHistory(listing_id=row.id, price=price, in_stock=True,
                                    checked_at=now - timedelta(hours=hours_ago)))
        return row

    old = listing(v1, amazon, 9000, 72)
    listing(v1, bkm, 15000, 1)
    recent = listing(v2, amazon, 8000, 2)
    # The recent Amazon listing also has a price from 3 days ago.
    db_session.add(PriceHistory(listing_id=recent.id, price=8500, in_stock=True, checked_at=now - timedelta(hours=72)))
    listing(v2, bkm, 15000, 1)
    listing(v3, amazon, 7000, 72)
    db_session.add_all([
        ListingChange(created_at=now - timedelta(hours=72), volume_id=v1.id, store_id=amazon.id, kind="new"),
        ListingChange(created_at=now - timedelta(hours=72), volume_id=v1.id, store_id=bkm.id, kind="new"),
    ])
    db_session.commit()
    return series, v1, v2, v3, old, recent


def test_old_amazon_price_is_not_shown(client, db_session, amazon_case):
    series, v1, v2, v3, old, recent = amazon_case
    stores = {s["store"]: s["price"] for s in client.get(f"/volume/{v1.id}").json()["stores"]}
    assert stores == {"BKM Kitap": 150.0}
    stores = {s["store"]: s["price"] for s in client.get(f"/volume/{v2.id}").json()["stores"]}
    assert stores == {"Amazon": 80.0, "BKM Kitap": 150.0}
    assert client.get(f"/volume/{v3.id}").json()["stores"] == []

    # Series rows, search summary and the alert mail ignore it too.
    stats = catalog_service.get_series(db_session, series.id).volume_stats
    assert (stats[v1.id].best_price_cents, stats[v3.id].best_price_cents) == (15000, None)
    assert catalog_service.series_offer_summary(db_session, [series.id]) == {series.id: (3, 8000)}
    assert best_offer(db_session, v1.id).price == 15000
    assert best_offer(db_session, v3.id) is None

    # The chart keeps only the last 24 hours of Amazon prices.
    history = catalog_service.get_price_history(db_session, v2.id)
    amazon_points = [p.price for e in history.entries if e.listing.id == recent.id for p in e.points]
    assert amazon_points == [8000]


def test_purge_deletes_old_amazon_prices(db_session, amazon_case):
    _, v1, v2, v3, old, recent = amazon_case
    assert purge_expired_prices(db_session) == {"amazon": 2}
    amazon_id = db_session.query(Store.id).filter(Store.code == "amazon").scalar()
    left = db_session.query(StoreListing).filter(StoreListing.store_id == amazon_id).all()
    assert [l.id for l in left] == [recent.id]
    assert [p.price for p in db_session.query(PriceHistory).filter(PriceHistory.listing_id == recent.id)] == [8000]
    assert db_session.query(PriceHistory).filter(PriceHistory.listing_id == old.id).count() == 0
    # Other stores keep everything.
    assert db_session.query(ListingChange).filter(ListingChange.store_id == amazon_id).count() == 0
    assert db_session.query(ListingChange).count() == 1
    assert db_session.query(StoreListing).count() == 3


def test_rule_can_be_turned_off(db_session, amazon_case, monkeypatch):
    """STORE_PRICE_MAX_AGE_HOURS="" (no limits): Amazon shows like any store."""
    monkeypatch.setattr(catalog_service, "price_max_age", lambda: {})
    _, v1, *_ = amazon_case
    assert {l.store.code for l in catalog_service.get_volume(db_session, v1.id).listings} == {"amazon", "bkm"}
