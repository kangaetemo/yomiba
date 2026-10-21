"""One freshness rule for every price a visitor sees.

A listing whose store kept being refreshed while the listing itself was not
seen (Kitapsepeti drops sold-out products from search) keeps its frozen
"in stock". The volume page and the alert mail already ignore it
(``stale_listing_ids``); personal lists, search and the home feed must give
the same answer, or the wishlist total, the "Sadece stokta" filter and the
"Hedefte" badge show a price nobody can buy at.
"""

from __future__ import annotations

from datetime import timedelta

import pytest

from app.models import PriceAlert, Store, StoreListing, WishlistItem
from app.services import catalog_service
from app.services.price_alert_checker import best_offer
from app.utils import utcnow
from tests.test_import_service import seed_catalog_series


@pytest.fixture()
def stale_case(db_session):
    """v1: stale 100 TL at Kitapsepeti, fresh 150 TL at BKM.
    v2: fresh 120 TL at Kitapsepeti (keeps that store's newest check recent).
    v3: only a stale 90 TL listing at Kitapsepeti."""
    now = utcnow()
    series = seed_catalog_series(db_session, "Tazelik Manga", "Tazelik Yayin", volumes=(1, 2, 3))
    v1, v2, v3 = sorted(series.volumes, key=lambda v: v.volume_number)
    ks, bkm = Store(code="kitapsepeti", name="Kitapsepeti"), Store(code="bkm", name="BKM Kitap")
    db_session.add_all([ks, bkm])
    db_session.flush()

    def listing(volume, store, price, hours_ago):
        db_session.add(StoreListing(volume_id=volume.id, store_id=store.id, product_url=f"https://x/{volume.id}/{store.id}",
                                    price=price, in_stock=True, last_checked=now - timedelta(hours=hours_ago)))

    listing(v1, ks, 10000, 24 * 30)
    listing(v1, bkm, 15000, 1)
    listing(v2, ks, 12000, 1)
    listing(v3, ks, 9000, 24 * 30)
    for v in (v1, v2, v3):
        db_session.add(WishlistItem(user_id=1, volume_id=v.id))
        db_session.add(PriceAlert(user_id=1, volume_id=v.id, threshold_price=11000))
    db_session.commit()
    return series, v1, v2, v3


def test_personal_lists_skip_stale_listings(client, stale_case):
    _, v1, v2, v3 = stale_case
    expected = {v1.id: 150.0, v2.id: 120.0, v3.id: None}
    for path in ("/me/wishlist", "/me/price-alerts"):
        got = {i["volume_id"]: i["best_price"] for i in client.get(path).json()}
        assert got == expected, path
    client.patch(f"/volume/{v1.id}/collection-status", json={"status": "missing"})
    assert [i["best_price"] for i in client.get("/me/collection").json()] == [150.0]


def test_personal_lists_match_volume_page_and_alert(client, db_session, stale_case):
    """The list price is exactly what the alert mail would quote and the
    volume page counts as in stock."""
    _, v1, v2, v3 = stale_case
    alerts = {i["volume_id"]: i["best_price"] for i in client.get("/me/price-alerts").json()}
    for v in (v1, v2, v3):
        offer = best_offer(db_session, v.id)
        assert alerts[v.id] == (offer.price / 100 if offer else None)
        detail = catalog_service.get_volume(db_session, v.id)
        in_stock = [l for l in detail.listings if l.in_stock and l.id not in detail.stale_ids]
        assert alerts[v.id] == (min(l.price for l in in_stock) / 100 if in_stock else None)


def test_search_and_series_summary_skip_stale_listings(client, db_session, stale_case):
    series, v1, _, v3 = stale_case
    # The stale listings would make it (4, 9000): 4 offers, lowest 90 TL.
    assert catalog_service.series_offer_summary(db_session, [series.id]) == {series.id: (2, 12000)}
    hits = {h.volume.id: (h.in_stock_count, h.best_price_cents)
            for h in catalog_service.search_volumes(db_session, "tazelik manga 1")}
    assert hits == {v1.id: (1, 15000)}
    hits = {h.volume.id: (h.in_stock_count, h.best_price_cents)
            for h in catalog_service.search_volumes(db_session, "tazelik manga 3")}
    assert hits == {v3.id: (0, None)}


def test_store_down_as_a_whole_keeps_its_listings(client, db_session):
    """Staleness is relative to the store's own newest check: a store whose
    every listing is equally old (blocked, down) is not hidden."""
    series = seed_catalog_series(db_session, "Kapali Magaza", "Kapali Yayin", volumes=(1,))
    store = Store(code="dr", name="D&R")
    db_session.add(store)
    db_session.flush()
    db_session.add(StoreListing(volume_id=series.volumes[0].id, store_id=store.id, product_url="https://x/dr",
                                price=8000, in_stock=True, last_checked=utcnow() - timedelta(days=20)))
    db_session.add(WishlistItem(user_id=1, volume_id=series.volumes[0].id))
    db_session.commit()
    assert [i["best_price"] for i in client.get("/me/wishlist").json()] == [80.0]
    assert catalog_service.series_offer_summary(db_session, [series.id]) == {series.id: (1, 8000)}
