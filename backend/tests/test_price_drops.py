"""GET /price-drops — regression tests for the observed-price-drop feed.

The feed is read-only: it must report exactly the drops recorded in
price_history (a row lower than its predecessor for the same listing)
within the requested window, and nothing else — no rises, no first
observations, nothing stale.
"""

from __future__ import annotations

from datetime import timedelta

from app.models import PriceHistory, Publisher, Series, Store, StoreListing, Volume
from app.utils import utcnow


def _seed(db_session, *, title: str = "Düşen Manga", store_code: str = "bkm") -> StoreListing:
    """Publisher + series + volume + one store listing; returns the listing."""
    stores = [Store(code=store_code, name=f"{store_code.upper()} Kitap")]
    db_session.add_all(stores)
    db_session.flush()
    pub_key = title.lower().replace(" ", "-")
    publisher = Publisher(name=pub_key.title(), normalized_name=pub_key)
    db_session.add(publisher)
    db_session.flush()
    series = Series(
        publisher_id=publisher.id,
        title=title,
        slug=title.lower().replace(" ", "-"),
        normalized_title=title.lower().replace(" ", "-"),
    )
    db_session.add(series)
    db_session.flush()
    vol = Volume(series_id=series.id, volume_number=1)
    db_session.add(vol)
    db_session.flush()
    listing = StoreListing(
        volume_id=vol.id,
        store_id=stores[0].id,
        product_url="https://bkm.example/p/1",
    )
    db_session.add(listing)
    db_session.flush()
    db_session.commit()
    return listing


def _history(db_session, listing: StoreListing, price_cents: int, when=None) -> PriceHistory:
    h = PriceHistory(
        listing_id=listing.id, price=price_cents, checked_at=when or utcnow()
    )
    db_session.add(h)
    db_session.commit()
    return h


class TestPriceDrops:
    def test_drop_is_reported_with_correct_numbers(self, db_session, client):
        listing = _seed(db_session)
        _history(db_session, listing, 14990, when=utcnow() - timedelta(hours=2))
        _history(db_session, listing, 9990)  # 149.90 -> 99.90 = 33%

        body = client.get("/price-drops").json()
        assert body["window_hours"] == 24
        drops = body["drops"]
        assert len(drops) == 1
        d = drops[0]
        assert d["series_title"] == "Düşen Manga"
        assert d["store_name"] == "BKM Kitap"
        assert d["old_price"] == 149.90
        assert d["new_price"] == 99.90
        assert d["drop_pct"] == 33
        assert d["volume_number"] == 1
        assert d["in_stock"] is True

    def test_sold_out_listing_drop_is_not_reported(self, db_session, client):
        """A drop on a listing that is now out of stock is not a deal."""
        listing = _seed(db_session)
        _history(db_session, listing, 14990, when=utcnow() - timedelta(hours=2))
        _history(db_session, listing, 9990)
        listing.in_stock = False
        db_session.commit()

        assert client.get("/price-drops").json()["drops"] == []

    def test_price_rise_is_not_reported(self, db_session, client):
        listing = _seed(db_session)
        _history(db_session, listing, 9990, when=utcnow() - timedelta(hours=2))
        _history(db_session, listing, 14990)  # rise, not a drop

        assert client.get("/price-drops").json()["drops"] == []

    def test_first_observation_is_not_reported(self, db_session, client):
        listing = _seed(db_session)
        _history(db_session, listing, 9990)  # no predecessor to compare with

        assert client.get("/price-drops").json()["drops"] == []

    def test_equal_price_is_not_reported(self, db_session, client):
        listing = _seed(db_session)
        _history(db_session, listing, 9990, when=utcnow() - timedelta(hours=2))
        _history(db_session, listing, 9990)

        assert client.get("/price-drops").json()["drops"] == []

    def test_drop_outside_window_is_excluded(self, db_session, client):
        listing = _seed(db_session)
        _history(db_session, listing, 14990, when=utcnow() - timedelta(hours=72))
        _history(db_session, listing, 9990, when=utcnow() - timedelta(hours=70))

        assert client.get("/price-drops").json()["drops"] == []
        # ...but a wider window finds it.
        body = client.get("/price-drops?hours=96").json()
        assert len(body["drops"]) == 1

    def test_newest_drop_first_and_limit(self, db_session, client):
        listing_a = _seed(db_session, title="İlk Seri", store_code="bkm")
        listing_b = _seed(db_session, title="İkinci Seri", store_code="dr")
        # listing_a drops oldest, listing_b drops newest
        _history(db_session, listing_a, 10000, when=utcnow() - timedelta(hours=3))
        _history(db_session, listing_a, 5000, when=utcnow() - timedelta(hours=2))
        _history(db_session, listing_b, 20000, when=utcnow() - timedelta(hours=2))
        _history(db_session, listing_b, 10000)

        body = client.get("/price-drops").json()
        titles = [d["series_title"] for d in body["drops"]]
        assert titles == ["İkinci Seri", "İlk Seri"]

        body = client.get("/price-drops?limit=1").json()
        assert len(body["drops"]) == 1
        assert body["drops"][0]["series_title"] == "İkinci Seri"

    def test_same_listing_dropped_twice_reports_both(self, db_session, client):
        listing = _seed(db_session)
        _history(db_session, listing, 20000, when=utcnow() - timedelta(hours=5))
        _history(db_session, listing, 10000, when=utcnow() - timedelta(hours=4))
        _history(db_session, listing, 5000, when=utcnow() - timedelta(hours=1))

        body = client.get("/price-drops").json()
        pairs = [(d["old_price"], d["new_price"]) for d in body["drops"]]
        assert pairs == [(100.0, 50.0), (200.0, 100.0)]
