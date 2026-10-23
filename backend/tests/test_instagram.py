"""GET /admin/instagram/releases: releases in a window with every store's offer."""

from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.models import Store, StoreListing, User, Volume, WishlistItem
from tests.test_import_service import seed_catalog_series


def _vol(db_session, series, number):
    return db_session.scalar(select(Volume).where(Volume.series_id == series.id,
                                                  Volume.volume_number == number))


def _offer(db_session, volume, store, price, in_stock=True):
    db_session.add(StoreListing(volume_id=volume.id, store_id=store.id, price=price, in_stock=in_stock,
                                product_url=f"https://{store.code}.example/{volume.id}"))
    db_session.flush()


def test_releases_with_offers_per_store(client, db_session):
    bkm, ks, dr = Store(code="bkm", name="BKM Kitap"), Store(code="ks", name="Kitapsec"), Store(code="dr", name="D&R")
    db_session.add_all([bkm, ks, dr])
    berserk = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1, 2))
    zom = seed_catalog_series(db_session, "Zom 100", "Marmara Çizgi", volumes=(1,))
    b1, b2, z1 = _vol(db_session, berserk, 1), _vol(db_session, berserk, 2), _vol(db_session, zom, 1)
    b1.release_date = date(2026, 10, 20)
    z1.release_date = date(2026, 10, 22)
    b2.release_date = date(2026, 10, 27)  # next week: outside the window
    _offer(db_session, b1, bkm, 16900)
    _offer(db_session, b1, ks, 14500)
    _offer(db_session, b1, dr, 9900, in_stock=False)  # sold out: not an offer
    user = db_session.scalar(select(User))
    db_session.add(WishlistItem(user_id=user.id, volume_id=z1.id))
    db_session.commit()

    body = client.get("/admin/instagram/releases?start=2026-10-20&end=2026-10-26").json()

    assert [(v["series_title"], v["number"]) for v in body["volumes"]] == [("Berserk", 1), ("Zom 100", 1)]
    berserk1, zom1 = body["volumes"]
    assert berserk1["offers"] == [
        {"store": "Kitapsec", "store_code": "ks", "price": 145.0},
        {"store": "BKM Kitap", "store_code": "bkm", "price": 169.0},
    ]
    assert berserk1["lowest_price"] == 145.0 and berserk1["in_stock_offers"] == 2
    assert berserk1["publisher"] == "Athica" and berserk1["release_date"] == "2026-10-20"
    assert zom1["offers"] == [] and zom1["lowest_price"] is None
    assert zom1["interest"] > berserk1["interest"] == 0


def test_window_is_limited_and_admin_only(client, db_session):
    assert client.get("/admin/instagram/releases?start=2026-10-26&end=2026-10-20").status_code == 422
    assert client.get("/admin/instagram/releases?start=2026-10-01&end=2026-11-15").status_code == 422
    client.cookies.clear()
    assert client.get("/admin/instagram/releases?start=2026-10-20&end=2026-10-26").status_code == 401
