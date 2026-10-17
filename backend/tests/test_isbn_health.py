"""Read-only ISBN health report: each check flags its case and nothing is written."""
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models import IsbnChange, Store, StoreListing, StoreObservation, Volume
from app.normalization.isbn import catalog_book_isbn, isbn_checksum_ok
from tests.test_import_service import seed_catalog_series

HAPPINESS_5 = "9786259360492"
HAPPINESS_6 = "9786259324050"
BL28, BL29 = "9786258630626", "9786258630633"


def test_checksum_and_catalog_isbn():
    assert isbn_checksum_ok(HAPPINESS_5) and isbn_checksum_ok(HAPPINESS_6)
    assert not isbn_checksum_ok("9786259324051")
    assert isbn_checksum_ok("0306406152") and not isbn_checksum_ok("0306406153")
    assert catalog_book_isbn("978-625-93240-5-0") == HAPPINESS_6
    assert catalog_book_isbn("9740202402059") is None  # store barcode
    assert catalog_book_isbn("9781421569147") is None  # VIZ English edition


def _listing(db, volume, store, url, price, in_stock=True):
    db.add(StoreListing(volume_id=volume.id, store_id=store.id, product_url=url, price=price,
                        in_stock=in_stock, last_checked=datetime.now(timezone.utc)))


def test_health_report_flags_each_case(client, db_session):
    happiness = seed_catalog_series(db_session, "Happiness", "Kayıp Kıta", volumes=(4, 5, 6))
    skip = seed_catalog_series(db_session, "Skip and Loafer", "Kayıp Kıta", volumes=(1, 2, 3, 4, 5))
    blue = seed_catalog_series(db_session, "Blue Lock", "Komikşeyler", volumes=(28, 29))
    vols = {v.volume_number: v for v in db_session.scalars(select(Volume).where(Volume.series_id == happiness.id))}
    skips = {v.volume_number: v for v in db_session.scalars(select(Volume).where(Volume.series_id == skip.id))}
    blues = {v.volume_number: v for v in db_session.scalars(select(Volume).where(Volume.series_id == blue.id))}
    for v in [*vols.values(), *skips.values(), *blues.values()]:
        v.catalog_present = v.catalog_released = True
    vols[5].isbn = HAPPINESS_5
    vols[6].isbn, vols[6].catalog_isbn = HAPPINESS_6, HAPPINESS_5    # Mangakol's off-by-one
    blues[28].catalog_isbn = blues[29].catalog_isbn = BL28           # source duplicate
    skips[1].isbn = "9786259324051"                                   # bad check digit
    stores = [Store(code=f"s{i}", name=f"Mağaza {i}") for i in range(4)]
    db_session.add_all(stores)
    db_session.flush()
    # Cilt 4: one store far above the others.
    for store, price in zip(stores, (20000, 21000, 20500, 60000)):
        _listing(db_session, vols[4], store, f"https://{store.code}.example/happiness-4", price)
    # Skip and Loafer 5 priced like a limited edition next to 200 TL volumes.
    for n, price in ((1, 20000), (2, 20000), (3, 21000), (4, 20000), (5, 90000)):
        _listing(db_session, skips[n], stores[1], f"https://b.example/skip-and-loafer-{n}", price)
    now = datetime.now(timezone.utc)
    db_session.add(StoreObservation(store_id=stores[2].id, product_url="https://c.example/yubooh-2",
                                    title="Blue Lock Cilt 28", isbn=BL29, title_volume_id=blues[28].id,
                                    isbn_volume_id=blues[29].id, volume_id=blues[28].id, rule="title_over_isbn",
                                    first_seen=now, last_seen=now))
    db_session.add(IsbnChange(volume_id=vols[5].id, old_isbn=None, new_isbn=HAPPINESS_5, source="catalog",
                              reason="Mangakol katalog ISBN'i", created_at=now))
    db_session.commit()
    listings_before = db_session.scalar(select(func.count()).select_from(StoreListing))

    response = client.get("/admin/isbn/health")
    assert response.status_code == 200
    report = response.json()
    checks = report["checks"]

    assert report["totals"]["released_without_isbn"] == 7  # Happiness 4, Skip 2–5, Blue Lock 28–29
    assert [(r["volume_number"], r["kind"]) for r in checks["catalog_differs"]["items"]] == [(6, "differs"), (28, "empty"), (29, "empty")]
    dup = checks["catalog_duplicate"]["items"]
    assert len(dup) == 1 and dup[0]["isbn"] == BL28 and {v["volume_number"] for v in dup[0]["volumes"]} == {28, 29}
    conflict = checks["title_isbn_conflict"]["items"][0]
    assert (conflict["title_volume"]["volume_number"], conflict["isbn_volume"]["volume_number"]) == (28, 29)
    outlier = checks["listing_price_outlier"]["items"]
    assert len(outlier) == 1 and outlier[0]["price"] == 600.0 and outlier[0]["volume_number"] == 4
    assert [(r["series"], r["volume_number"]) for r in checks["volume_price_outlier"]["items"]] == [("Skip and Loafer", 5)]
    assert [(r["volume_number"], r["problem"]) for r in checks["invalid_isbn"]["items"]] == [(1, "checksum")]
    assert checks["recent_changes"]["items"][0]["new_isbn"] == HAPPINESS_5

    # Read-only: no ISBN written, no listing touched.
    db_session.expire_all()
    assert db_session.get(Volume, vols[6].id).isbn == HAPPINESS_6
    assert db_session.get(Volume, blues[28].id).isbn is None
    assert db_session.scalar(select(func.count()).select_from(StoreListing)) == listings_before


def test_health_report_requires_admin(client):
    client.cookies.clear()
    assert client.get("/admin/isbn/health").status_code == 401
