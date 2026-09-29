"""GET /home shelves, the lowest-ever flag on /price-drops and the catalog
details on GET /volume/{id}."""

from __future__ import annotations

from datetime import date, timedelta

from sqlalchemy import select

from app.models import PriceHistory, Series, Store, StoreListing, User, Volume, WishlistItem
from tests.test_import_service import seed_catalog_series


def _vol(db_session, series, number):
    return db_session.scalar(select(Volume).where(Volume.series_id == series.id,
                                                  Volume.volume_number == number))


def _offer(db_session, volume, store, price, in_stock=True):
    listing = StoreListing(volume_id=volume.id, store_id=store.id, price=price, in_stock=in_stock,
                           product_url=f"https://{store.code}.example/{volume.id}")
    db_session.add(listing)
    db_session.flush()
    return listing


def test_home_popular_series_and_new_volumes(client, db_session):
    bkm, ks = Store(code="bkm", name="BKM"), Store(code="ks", name="Kitapsec")
    db_session.add_all([bkm, ks])
    berserk = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1, 2))
    zom = seed_catalog_series(db_session, "Zom 100", "Marmara Çizgi", volumes=(1,))
    quiet = seed_catalog_series(db_session, "Sessiz Seri", "X", volumes=(1,))
    berserk.author = "Kentaro Miura"
    _offer(db_session, _vol(db_session, berserk, 1), bkm, 16900)
    _offer(db_session, _vol(db_session, berserk, 2), ks, 15500)
    _offer(db_session, _vol(db_session, zom, 1), bkm, 12000)
    _offer(db_session, _vol(db_session, quiet, 1), bkm, 9000, in_stock=False)  # no in-stock offer
    # reader interest outranks raw offer count
    user = db_session.scalar(select(User))
    db_session.add(WishlistItem(user_id=user.id, volume_id=_vol(db_session, zom, 1).id))
    today = date.today()
    _vol(db_session, berserk, 2).release_date = today - timedelta(days=3)
    _vol(db_session, zom, 1).release_date = today - timedelta(days=1)
    _vol(db_session, berserk, 1).release_date = today + timedelta(days=30)  # announced
    db_session.commit()

    body = client.get("/home").json()

    popular = body["popular_series"]
    assert [s["title"] for s in popular] == ["Zom 100", "Berserk"]
    assert popular[1]["lowest_price"] == 155.0 and popular[1]["volume_count"] == 2
    assert popular[1]["author"] == "Kentaro Miura"

    new = body["new_volumes"]
    assert [(v["series_title"], v["number"]) for v in new] == [("Zom 100", 1), ("Berserk", 2)]
    assert new[0]["release_date"] == (today - timedelta(days=1)).isoformat()
    assert body["stats"]["series"] == 3 and body["stats"]["stores"] == 2


def test_price_drops_flag_lowest_ever(client, db_session):
    store = Store(code="bkm", name="BKM")
    db_session.add(store)
    series = seed_catalog_series(db_session, "Berserk", "Athica", volumes=(1, 2))
    a = _offer(db_session, _vol(db_session, series, 1), store, 14000)
    b = _offer(db_session, _vol(db_session, series, 2), store, 15000)
    for listing, prices in ((a, (13000, 16000, 14000)), (b, (16000, 15000))):
        for p in prices:
            db_session.add(PriceHistory(listing_id=listing.id, price=p))
    db_session.commit()

    drops = {d["listing_id"]: d for d in client.get("/price-drops").json()["drops"]}
    assert drops[a.id]["lowest_ever"] is False  # 130 was seen before
    assert drops[b.id]["lowest_ever"] is True


def test_volume_detail_exposes_catalog_details(client, db_session):
    series = seed_catalog_series(db_session, "Dragon Ball", "Gerekli Şeyler", volumes=(5,))
    series_row = db_session.get(Series, series.id)
    series_row.author = series_row.illustrator = "Akira Toriyama"
    vol = _vol(db_session, series, 5)
    vol.isbn, vol.page_count, vol.release_date = "9786258237337", 388, date(2023, 6, 22)
    vol.covers_from, vol.covers_to = 9, 10
    db_session.commit()

    body = client.get(f"/volume/{vol.id}").json()
    assert body["isbn"] == "9786258237337" and body["page_count"] == 388
    assert body["release_date"] == "2023-06-22"
    assert (body["covers_from"], body["covers_to"]) == (9, 10)
    assert body["series"]["author"] == "Akira Toriyama"
