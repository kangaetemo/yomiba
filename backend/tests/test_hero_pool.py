"""The discovery pool is independent of the ranked popularity shelf."""
from sqlalchemy import select

from app.models import CatalogSeries, Store
from tests.test_home_feed import _offer, _vol
from tests.test_import_service import seed_catalog_series


def test_hero_pool_includes_catalog_series_outside_popular_limit(client, db_session):
    store = Store(code="hero", name="Hero Store")
    db_session.add(store)
    db_session.flush()
    ids = []
    for number in range(27):
        series = seed_catalog_series(db_session, f"Keşif {number}", "Athica", volumes=(0,))
        volume = _vol(db_session, series, 0)
        volume.cover_key = f"v/{volume.id}-012345abcdef.webp"
        _offer(db_session, volume, store, 12000)
        ids.append(series.id)
    db_session.commit()
    default = client.get("/home?popular=1").json()
    assert "hero_series" not in default
    body = client.get("/home?popular=1&hero=true").json()
    assert body["popular_series"] == default["popular_series"]
    assert {s["id"] for s in body["hero_series"]} == set(ids)
    assert len(body["hero_series"]) > 24
    assert all(s["cover_url"] and s["lowest_price"] == 120.0 and s["slug"] for s in body["hero_series"])


def test_hero_pool_requires_cover_in_stock_price_and_catalog_membership(client, db_session):
    store = Store(code="hero", name="Hero Store")
    db_session.add(store)
    db_session.flush()
    for title, price, stock, covered, catalog in [
        ("Uygun", 10000, True, True, True),
        ("Kapaksız", 10000, True, False, True),
        ("Tükendi", 10000, False, True, True),
        ("Fiyatsız", None, True, True, True),
        ("Katalog dışı", 10000, True, True, False),
    ]:
        series = seed_catalog_series(db_session, title, "Athica")
        volume = _vol(db_session, series, 1)
        if covered:
            volume.cover_key = f"v/{volume.id}-012345abcdef.webp"
        _offer(db_session, volume, store, price, in_stock=stock)
        if not catalog:
            db_session.delete(db_session.scalar(select(CatalogSeries).where(CatalogSeries.series_id == series.id)))
    db_session.commit()
    body = client.get("/home?hero=true").json()
    assert [s["title"] for s in body["hero_series"]] == ["Uygun"]


def test_hero_pool_handles_empty_catalog(client):
    assert client.get("/home?hero=true").json()["hero_series"] == []
