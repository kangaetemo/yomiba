"""GET /import/coverage — shelf-health summary for the admin panel."""

from __future__ import annotations

from datetime import timedelta

from app.models import (
    CatalogSeries,
    ImportRecord,
    Publisher,
    Series,
    Store,
    StoreListing,
    Volume,
)
from app.utils import utcnow


def _seed_shelf(db_session, *, with_listing: bool = True) -> None:
    """Publisher + 2 catalog series (alpha/beta); alpha gets a volume and,
    optionally, two store listings (one per store — (volume, store) is
    unique)."""
    stores = [Store(code="bkm", name="BKM Kitap"), Store(code="dr", name="D&R")]
    db_session.add_all(stores)
    db_session.flush()
    publisher = Publisher(name="T Publisher", normalized_name="t publisher")
    db_session.add(publisher)
    db_session.flush()
    alpha = None
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
        if slug == "alpha":
            alpha = s
    if with_listing:
        vol = Volume(series_id=alpha.id, volume_number=1)
        db_session.add(vol)
        db_session.flush()
        for i, (store, price) in enumerate(zip(stores, [1000, 1200])):
            db_session.add(
                StoreListing(
                    volume_id=vol.id,
                    store_id=store.id,
                    product_url=f"https://example.com/p{i}",
                    price=price,
                    last_checked=utcnow(),
                )
            )
    db_session.commit()


def _record(session, key, **kw) -> ImportRecord:
    now = utcnow()
    record = ImportRecord(
        normalized_query=key,
        last_query=kw.get("last_query", key),
        status=kw.get("status", "success"),
        last_attempt_at=kw.get("last_attempt_at", now),
        last_success_at=kw.get("last_success_at", now),
        stores_ok=kw.get("stores_ok", 3),
        stores_failed=kw.get("stores_failed", 0),
        results_found=kw.get("results_found", 10),
        created=kw.get("created", 0),
        updated=kw.get("updated", 0),
        error=kw.get("error"),
    )
    session.add(record)
    return record


def test_coverage_empty_db(client, db_session):
    body = client.get("/import/coverage").json()
    assert body["catalog_series"] == 0
    assert body["series_with_listings"] == 0
    assert body["listings_total"] == 0
    assert body["records_total"] == 0
    assert body["records_by_status"] == {}
    assert body["fresh_records"] == 0
    assert body["freshness_ttl_minutes"] == 60


def test_coverage_counts(client, db_session):
    _seed_shelf(db_session, with_listing=True)
    now = utcnow()
    _record(db_session, "alpha", status="success")  # fresh
    _record(
        db_session,
        "beta",
        status="partial",
        last_success_at=now - timedelta(hours=2),  # stale
        stores_failed=2,
    )
    _record(
        db_session,
        "gamma",
        status="failed",
        last_success_at=None,
        stores_ok=0,
        stores_failed=7,
        error="boom",
    )
    db_session.commit()

    body = client.get("/import/coverage").json()
    assert body["catalog_series"] == 2
    assert body["series_with_listings"] == 1  # only alpha has a listing
    assert body["listings_total"] == 2
    assert body["records_total"] == 3
    assert body["records_by_status"] == {
        "success": 1,
        "partial": 1,
        "failed": 1,
    }
    assert body["fresh_records"] == 1


def test_coverage_series_without_listing_not_counted(client, db_session):
    _seed_shelf(db_session, with_listing=False)
    body = client.get("/import/coverage").json()
    assert body["catalog_series"] == 2
    assert body["series_with_listings"] == 0
    assert body["listings_total"] == 0
