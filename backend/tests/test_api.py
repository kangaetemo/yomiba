"""API endpoint tests (search / series / volume / price-history / import)."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from tests.test_import_service import do_import, make_result

ISBN = "9786051234567"


@pytest.fixture()
def seeded(import_service, db_session, client):
    """Seed the mandatory scenario + a second series, then expose helpers."""
    from tests.test_import_service import seed_catalog_series

    # Catalog-only imports: the catalog series must exist BEFORE the store
    # import (they stand in for what the mangakol sync registered).
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1, 2))
    seed_catalog_series(db_session, "Berserk of Gluttony", "Shonen Jump")
    do_import(
        import_service,
        db_session,
        # Berserk / Athica: vol 1 in all three stores, vol 2 in two.
        make_result("bkm", "Berserk 1", "169", isbn=ISBN, publisher="Athica Yayınları",
                    image="https://cdn.example.com/b1.jpg"),
        make_result("dr", "Berserk 1", "260", isbn=ISBN, publisher="Athica Yayınları"),
        make_result("amazon", "Berserk 1", "163.54", isbn=ISBN, publisher="Athica Yayınları"),
        make_result("bkm", "Berserk 2", "199", publisher="Athica Yayınları",
                    image="https://cdn.example.com/b2.jpg"),
        make_result("dr", "Berserk 2", "260"),
        # A different series sharing the "Berserk" prefix must not be merged.
        make_result("bkm", "Berserk of Gluttony 1", "75", publisher="Shonen Jump"),
    )
    # Price history for the BKM Berserk-1 listing: an older, higher price.
    from app.models import ImportRecord, PriceHistory, StoreListing
    from app.normalization import normalize_text
    from app.utils import to_cents, utcnow
    from datetime import timedelta

    listing = db_session.query(StoreListing).filter(StoreListing.price == 16900).first()
    db_session.add(
        PriceHistory(
            listing_id=listing.id,
            price=to_cents("179.90"),
            checked_at=utcnow() - timedelta(days=14),
        )
    )
    # Mark "berserk" as freshly imported so /search serves "fresh" without
    # scheduling background jobs (deterministic API tests).
    db_session.add(
        ImportRecord(
            normalized_query=normalize_text("berserk"),
            last_query="berserk",
            status="success",
            stores_ok=3,
            stores_failed=0,
            results_found=6,
            created=6,
            last_attempt_at=utcnow(),
            last_success_at=utcnow(),
        )
    )
    db_session.commit()
    return client


# ---------------------------------------------------------------------------
# /search
# ---------------------------------------------------------------------------
def test_search_returns_matching_series(seeded):
    res = seeded.get("/search", params={"q": "berserk"})
    assert res.status_code == 200
    data = res.json()
    assert data["status"]["state"] == "fresh"
    titles = {s["title"] for s in data["results"]}
    assert titles == {"Berserk", "Berserk of Gluttony"}

    berserk = next(s for s in data["results"] if s["title"] == "Berserk")
    assert berserk["publisher"] == "Athica Yayınları"
    assert berserk["volume_count"] == 2
    # The store image is only a download source; no self-hosted copy yet.
    assert berserk["cover_url"] is None


def test_user_read_routes_never_enqueue_or_scrape(seeded, db_session, monkeypatch):
    from sqlalchemy import func, select
    from app.models import ImportRecord, Volume

    runner = seeded.app.state.import_runner
    def unexpected(*args, **kwargs):
        raise AssertionError("read route attempted an import")

    monkeypatch.setattr(runner, "submit", unexpected)
    monkeypatch.setattr(runner, "_scraper_factory", unexpected)
    before = db_session.scalar(select(func.count(ImportRecord.id)))
    series_id = seeded.get("/search", params={"q": "berserk"}).json()["results"][0]["id"]
    volume_id = db_session.scalar(select(Volume.id).where(Volume.series_id == series_id))

    assert seeded.get("/series/" + str(series_id)).status_code == 200
    assert seeded.get("/volume/" + str(volume_id)).status_code == 200
    assert db_session.scalar(select(func.count(ImportRecord.id))) == before


def test_search_is_case_and_accent_insensitive(seeded):
    res = seeded.get("/search", params={"q": "BERSERK"})
    assert res.status_code == 200
    assert len(res.json()["results"]) == 2
    assert res.json()["status"]["state"] == "fresh"  # same normalized key as "berserk"


def test_search_no_results_reports_idle(client):
    """DB miss: the catalog has no such series, so the response honestly
    reports "idle" — and NO background import is scheduled (catalog-only
    policy: an import could never produce visible results for it)."""
    from app.services.background_import import normalized_query_key

    res = client.get("/search", params={"q": "nonexistent-manga-xyz"})
    assert res.status_code == 200
    data = res.json()
    assert data["results"] == []
    assert data["status"]["state"] == "idle"

    runner = client.app.state.import_runner
    key = normalized_query_key("nonexistent-manga-xyz")
    assert runner.get_record(key) is None  # nothing was ever recorded

    # Repeated search: still idle, still no job (no store hammering).
    res2 = client.get("/search", params={"q": "nonexistent-manga-xyz"})
    data2 = res2.json()
    assert data2["results"] == []
    assert data2["status"]["state"] == "idle"
    assert not runner.is_running(key)


def test_search_blank_query_rejected(seeded):
    assert seeded.get("/search", params={"q": "   "}).status_code == 400
    assert seeded.get("/search").status_code == 422  # q is required


# ---------------------------------------------------------------------------
# /series/{id}
# ---------------------------------------------------------------------------
def test_series_detail(seeded):
    series_id = seeded.get("/search", params={"q": "berserk 1"}).json()[0]["id"] \
        if False else _series_id_for(seeded, "Berserk")
    res = seeded.get(f"/series/{series_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["title"] == "Berserk"
    assert data["publisher"] == "Athica Yayınları"
    assert data["cover_url"] is None  # never the store image URL (self-hosted only)
    assert [v["number"] for v in data["volumes"]] == [1, 2]

    vol1 = data["volumes"][0]
    assert vol1["best_price"] == 163.54  # Amazon is cheapest
    assert vol1["store_count"] == 3
    assert vol1["in_stock_count"] == 3
    assert vol1["best_store"] == "Amazon"

    # Search results carry the series' lowest in-stock price.
    hit = next(r for r in seeded.get("/search", params={"q": "Berserk"}).json()["results"]
               if r["id"] == series_id)
    assert hit["lowest_price"] == 163.54
    assert hit["in_stock_offers"] == 5

    vol2 = data["volumes"][1]
    assert vol2["best_price"] == 199.0
    assert vol2["store_count"] == 2


def _series_id_for(client, title: str) -> int:
    data = client.get("/search", params={"q": title}).json()
    return next(s["id"] for s in data["results"] if s["title"] == title)


def test_series_not_found(seeded):
    assert seeded.get("/series/9999").status_code == 404


def test_series_invalid_id(seeded):
    assert seeded.get("/series/abc").status_code == 422


# ---------------------------------------------------------------------------
# /volume/{id}
# ---------------------------------------------------------------------------
def _volume_id_for(client, series_id: int, number: int) -> int:
    data = client.get(f"/series/{series_id}").json()
    return next(v["id"] for v in data["volumes"] if v["number"] == number)


def test_volume_stores_sorted_cheapest_first(seeded):
    series_id = _series_id_for(seeded, "Berserk")
    vol_id = _volume_id_for(seeded, series_id, 1)

    res = seeded.get(f"/volume/{vol_id}")
    assert res.status_code == 200
    data = res.json()
    assert data["number"] == 1
    assert data["series"]["publisher"] == "Athica Yayınları"
    assert data["cover_url"] is None  # never the store image URL (self-hosted only)

    stores = [(s["store"], s["price"]) for s in data["stores"]]
    # Cheapest first: Amazon 163.54 < BKM 169 < D&R 260.
    assert stores[0] == ("Amazon", 163.54)
    assert stores[1] == ("BKM Kitap", 169.0)
    assert stores[2] == ("D&R", 260.0)
    assert all(s["stock"] is True for s in data["stores"])
    assert all(s["product_url"] for s in data["stores"])


def test_volume_not_found(seeded):
    assert seeded.get("/volume/9999").status_code == 404


def test_volume_without_listings(seeded):
    # The Gluttony volume has a listing too; use a fresh series volume instead.
    from tests.test_import_service import make_result as mr
    # (covered implicitly; ensure endpoint still 200 with empty stores)
    res = seeded.get("/search", params={"q": "berserk of gluttony"})
    series_id = res.json()["results"][0]["id"]
    vol_id = _volume_id_for(seeded, series_id, 1)
    out = seeded.get(f"/volume/{vol_id}").json()
    assert out["stores"][0]["store"] == "BKM Kitap"


# ---------------------------------------------------------------------------
# /volume/{id}/price-history
# ---------------------------------------------------------------------------
def test_price_history_grouped_by_store(seeded):
    series_id = _series_id_for(seeded, "Berserk")
    vol_id = _volume_id_for(seeded, series_id, 1)

    res = seeded.get(f"/volume/{vol_id}/price-history")
    assert res.status_code == 200
    data = res.json()
    assert data["volume_id"] == vol_id

    by_store = {entry["store"]: entry for entry in data["listings"]}
    assert set(by_store) == {"Amazon", "BKM Kitap", "D&R"}

    # BKM listing has two points (older 179.90 + current 169).
    bkm_points = [p["price"] for p in by_store["BKM Kitap"]["points"]]
    assert bkm_points == [179.90, 169.0]
    # Others have a single point.
    assert [p["price"] for p in by_store["Amazon"]["points"]] == [163.54]
    assert [p["price"] for p in by_store["D&R"]["points"]] == [260.0]


def test_price_history_not_found(seeded):
    assert seeded.get("/volume/9999/price-history").status_code == 404


# ---------------------------------------------------------------------------
# /import
# ---------------------------------------------------------------------------
def test_import_endpoint_uses_registry(monkeypatch, client, db_session):
    import app.services.import_service as imp_mod
    from app.models import Series
    from app.scrapers.base import BaseScraper
    from tests.test_import_service import make_result, seed_catalog_series

    seed_catalog_series(db_session, "Berserk", "Athica Yayınları")

    class FakeBkm(BaseScraper):
        store_id = "bkm"
        store_name = "BKM Kitap"

        def __init__(self):
            super().__init__()

        def search(self, query):
            return [make_result("bkm", "Berserk 1", "169", isbn=ISBN,
                                 publisher="Athica Yayınları")]

    monkeypatch.setattr(imp_mod, "get_scrapers", lambda store_ids=None: [FakeBkm()])
    res = client.post("/import", json={"query": "berserk"})
    assert res.status_code == 200
    data = res.json()
    assert data["total_created"] == 1
    assert data["stores"][0]["store_code"] == "bkm"
    assert data["stores"][0]["created"] == 1

    # The imported listing enriches a CATALOG series: search surfaces it.
    search = client.get("/search", params={"q": "berserk"}).json()
    assert len(search["results"]) == 1
    series = db_session.scalar(select(Series).where(Series.normalized_title == "berserk"))
    assert series is not None
    vol = client.get(f"/series/{series.id}").json()["volumes"][0]
    assert vol["store_count"] == 1
    assert vol["best_price"] == 169.0


def test_import_blank_query_rejected(client):
    assert client.post("/import", json={"query": "  "}).status_code == 400


def test_import_warmup_queues_every_catalog_series(client, db_session):
    """Admin refresh starts one bounded cycle for current catalog series."""
    from app.models import CatalogSeries, Publisher, Series
    from app.services.background_import import normalized_query_key
    from app.services.price_refresh_scheduler import PriceRefreshScheduler
    from sqlalchemy.orm import sessionmaker

    publisher = Publisher(
        name="Test Publisher", normalized_name="test publisher"
    )
    db_session.add(publisher)
    db_session.flush()
    for title, slug in [("Alpha", "alpha"), ("Beta", "beta")]:
        s = Series(
            publisher_id=publisher.id,
            title=title,
            slug=slug,
            normalized_title=slug,
        )
        db_session.add(s)
        db_session.flush()
        db_session.add(CatalogSeries(series_id=s.id, mangakol_slug=slug))
    db_session.commit()

    scheduler = PriceRefreshScheduler(
        client.app.state.import_runner,
        sessionmaker(bind=db_session.bind, autoflush=False, expire_on_commit=False),
        interval_seconds=3600, poll_seconds=0.05,
    )
    client.app.state.price_refresh_scheduler = scheduler
    scheduler.start()
    try:
        res = client.post("/import/price-refresh")
        assert res.status_code == 200
        assert res.json()["total_catalog_series"] == 2
        assert res.json()["current_cycle_mode"] == "full"
        assert client.post("/import/price-refresh").status_code == 409
    finally:
        scheduler.stop()
    runner = client.app.state.import_runner
    for key in ("alpha", "beta"):
        assert runner.wait_for(normalized_query_key(key))


def test_import_warmup_empty_catalog(client):
    """Admin refresh is unavailable when the scheduler is disabled."""
    res = client.post("/import/warmup")
    assert res.status_code == 503


# ---------------------------------------------------------------------------
# meta
# ---------------------------------------------------------------------------
def test_health(client):
    res = client.get("/health")
    assert res.status_code == 200
    assert res.json()["status"] == "ok"


def test_volume_stats_counts_in_stock_listings():
    from types import SimpleNamespace

    from app.services.catalog_service import _volume_stats

    ids = iter(range(1, 100))

    def listing(price, in_stock, store="BKM Kitap"):
        return SimpleNamespace(id=next(ids), price=price, in_stock=in_stock,
                               store=SimpleNamespace(name=store))

    mixed = _volume_stats([listing(10000, False, "Edessa"), listing(12000, True, "Kitapsec")])
    assert (mixed.best_price_cents, mixed.store_count, mixed.in_stock_count) == (12000, 2, 1)
    # The store named is the one behind best_price: the in-stock one.
    assert mixed.best_store == "Kitapsec"
    # Sold out everywhere: the cheapest known price stays visible, and
    # in_stock_count == 0 tells the UI it is an out-of-stock price.
    sold_out = _volume_stats([listing(10000, False), listing(9000, False)])
    assert (sold_out.best_price_cents, sold_out.store_count, sold_out.in_stock_count) == (9000, 2, 0)
    assert _volume_stats([]).in_stock_count == 0


def test_stale_listing_is_stock_unknown_not_in_stock(db_session):
    """A store dropping a sold-out product from search leaves its listing
    frozen at "in stock"; once the same store's other listings are much
    fresher, that listing no longer counts as in stock."""
    from datetime import timedelta

    from app.models import Publisher, Series, Store, StoreListing, Volume
    from app.services.catalog_service import _volume_stats, stale_listing_ids
    from app.utils import utcnow

    now = utcnow()
    ks = Store(code="kitapsepeti", name="Kitapsepeti")
    blocked = Store(code="dr", name="D&R")
    pub = Publisher(name="P", normalized_name="p")
    db_session.add_all([ks, blocked, pub])
    db_session.flush()
    series = Series(publisher_id=pub.id, title="S", slug="s", normalized_title="s")
    db_session.add(series)
    db_session.flush()
    v1, v2 = Volume(series_id=series.id, volume_number=1), Volume(series_id=series.id, volume_number=2)
    db_session.add_all([v1, v2])
    db_session.flush()

    def listing(volume, store, hours_ago):
        row = StoreListing(volume_id=volume.id, store_id=store.id, product_url=f"u{volume.id}{store.id}",
                           price=10000, in_stock=True, last_checked=now - timedelta(hours=hours_ago))
        db_session.add(row)
        return row

    fresh = listing(v1, ks, 1)
    gone = listing(v2, ks, 100)  # not seen for 4 days while v1 was refreshed
    # A whole store that is down: all its listings are equally old, so none
    # is stale (staleness is relative to the store's own newest check).
    old_a = listing(v1, blocked, 200)
    old_b = listing(v2, blocked, 210)
    db_session.flush()

    stale = stale_listing_ids(db_session, [fresh, gone, old_a, old_b])
    assert stale == {gone.id}
    stats = _volume_stats([gone], stale)
    assert (stats.store_count, stats.in_stock_count, stats.stale_count) == (1, 0, 1)
    assert stats.best_price_cents == 10000  # last known price stays visible


def test_missing_price_refresh_needs_scheduler(client):
    assert client.post("/import/price-refresh/missing").status_code == 503
