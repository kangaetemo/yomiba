"""GET /admin/instagram/releases: releases in a window with every store's offer."""

from __future__ import annotations

from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

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
    berserk.author = "Kentaro Miura"
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
    assert berserk1["author"] == "Kentaro Miura" and "jp_status" not in berserk1
    assert zom1["author"] is None
    assert zom1["offers"] == [] and zom1["lowest_price"] is None
    assert zom1["interest"] > berserk1["interest"] == 0


def test_window_is_limited_and_admin_only(client, db_session):
    assert client.get("/admin/instagram/releases?start=2026-10-26&end=2026-10-20").status_code == 422
    assert client.get("/admin/instagram/releases?start=2026-10-01&end=2026-11-15").status_code == 422
    client.cookies.clear()
    assert client.get("/admin/instagram/releases?start=2026-10-20&end=2026-10-26").status_code == 401


def test_launch_stats_and_price_spread_examples(client, db_session):
    stores = [Store(code=c, name=n) for c, n in (("bkm", "BKM Kitap"), ("ks", "Kitapsec"), ("dr", "D&R"))]
    db_session.add_all(stores)
    bkm, ks, dr = stores
    berserk = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1, 2))
    zom = seed_catalog_series(db_session, "Zom 100", "Marmara Çizgi", volumes=(1,))
    b1, b2, z1 = _vol(db_session, berserk, 1), _vol(db_session, berserk, 2), _vol(db_session, zom, 1)
    for store, price in ((bkm, 20000), (ks, 15000), (dr, 17000)):
        _offer(db_session, b1, store, price)
    for store, price in ((bkm, 12000), (ks, 11000), (dr, 11500)):
        _offer(db_session, z1, store, price)
    _offer(db_session, b2, bkm, 30000)
    _offer(db_session, b2, ks, 10000)  # two offers only: not an example
    db_session.commit()

    body = client.get("/admin/instagram/launch").json()

    assert body["stats"] == {"series": 2, "volumes": 3, "publishers": 2, "stores": 3, "offers": 8}
    assert [(v["series_title"], v["number"]) for v in body["examples"]] == [("Berserk", 1), ("Zom 100", 1)]
    assert [o["price"] for o in body["examples"][0]["offers"]] == [150.0, 170.0, 200.0]
    assert body["examples"][0]["release_date"] is None
    client.cookies.clear()
    assert client.get("/admin/instagram/launch").status_code == 401


def test_new_series_first_volumes_without_prices(client, db_session):
    today = datetime.now(ZoneInfo("Europe/Istanbul")).date()
    bkm = Store(code="bkm", name="BKM Kitap")
    db_session.add(bkm)
    dandadan = seed_catalog_series(db_session, "Dandadan", "Gerekli Şeyler", volumes=(1, 2))
    dandadan.author = "Yukinobu Tatsu"
    dandadan.jp_status = "ongoing"
    kaiju = seed_catalog_series(db_session, "Kaiju No. 8", "Gerekli Şeyler", volumes=(1,))
    berserk = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1, 2))
    d1, d2 = _vol(db_session, dandadan, 1), _vol(db_session, dandadan, 2)
    d1.release_date, d2.release_date = today - timedelta(days=10), today + timedelta(days=20)
    d2.description = "  Okarun ile Momo'nun hikâyesi.  "
    _vol(db_session, kaiju, 1).release_date = today + timedelta(days=14)  # announced
    _vol(db_session, berserk, 1).release_date = today - timedelta(days=400)  # long running
    _offer(db_session, d1, bkm, 15990)
    db_session.commit()

    body = client.get("/admin/instagram/new-series").json()

    assert [s["title"] for s in body["series"]] == ["Kaiju No. 8", "Dandadan"]
    kaiju8, dan = body["series"]
    assert kaiju8["upcoming"] is True and kaiju8["released_volumes"] == 0
    assert dan["upcoming"] is False and dan["released_volumes"] == 1
    assert dan["release_date"] == (today - timedelta(days=10)).isoformat()
    assert dan["author"] == "Yukinobu Tatsu" and dan["publisher"] == "Gerekli Şeyler"
    assert dan["description"] == "Okarun ile Momo'nun hikâyesi." and kaiju8["description"] is None
    assert not {"jp_status", "tr_status", "offers", "lowest_price"} & dan.keys()
    client.cookies.clear()
    assert client.get("/admin/instagram/new-series").status_code == 401
