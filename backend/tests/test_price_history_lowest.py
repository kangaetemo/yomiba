"""The price-history chart is one line: the lowest in-stock price over time."""
from datetime import datetime, timedelta, timezone

from sqlalchemy import select

from app.models import PriceHistory, Store, StoreListing, Volume
from tests.test_import_service import seed_catalog_series

T0 = datetime(2026, 9, 1, 9, tzinfo=timezone.utc)


def test_lowest_line_follows_the_cheapest_in_stock_store(client, db_session):
    series = seed_catalog_series(db_session, "Blue Lock", "Komikşeyler", volumes=(29,))
    vol = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    bkm, ks = Store(code="bkm", name="BKM Kitap"), Store(code="kitapsec", name="Kitapseç")
    db_session.add_all([bkm, ks])
    db_session.flush()
    a = StoreListing(volume_id=vol.id, store_id=bkm.id, product_url="https://bkm/29", price=20500, in_stock=True, last_checked=T0)
    b = StoreListing(volume_id=vol.id, store_id=ks.id, product_url="https://ks/29", price=19900, in_stock=True, last_checked=T0)
    db_session.add_all([a, b])
    db_session.flush()
    day = lambda n: T0 + timedelta(days=n)
    points = [
        (a, 21000, True, 0), (b, 19900, True, 0),   # Kitapseç cheapest
        (a, 17200, True, 5),                         # BKM campaign
        (a, 20500, True, 12),                        # campaign over -> Kitapseç again
        (b, 19900, False, 20),                       # Kitapseç sold out -> BKM
        (a, 20500, False, 25),                       # nobody in stock -> gap
        (b, 19900, True, 30), (b, 19900, True, 31),  # back; a repeat adds no step
    ]
    for listing, price, ok, n in points:
        db_session.add(PriceHistory(listing_id=listing.id, price=price, in_stock=ok, checked_at=day(n), product_url=listing.product_url))
    db_session.commit()

    lowest = client.get(f"/volume/{vol.id}/price-history").json()["lowest"]
    assert [(p["price"], p["store"]) for p in lowest] == [
        (199.0, "Kitapseç"), (172.0, "BKM Kitap"), (199.0, "Kitapseç"),
        (205.0, "BKM Kitap"), (None, None), (199.0, "Kitapseç"),
    ]
    assert lowest[1]["at"].startswith("2026-09-06")
