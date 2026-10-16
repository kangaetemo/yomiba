"""Read-only ISBN health report: each check flags its case and nothing is written."""
from datetime import datetime, timezone

from sqlalchemy import func, select

from app.models import Store, StoreListing, Volume
from app.services import catalog_state
from app.services.isbn_health import isbn_checksum_ok, url_volume_numbers
from tests.test_import_service import seed_catalog_series

HAPPINESS_5 = "9786259360492"  # Bora: Happiness 5; Mangakol also gave it to Cilt 6
HAPPINESS_6 = "9786259324050"
SKIP_4 = "9786259324036"


def test_checksum():
    assert isbn_checksum_ok(HAPPINESS_5) and isbn_checksum_ok(HAPPINESS_6)
    assert not isbn_checksum_ok("9786259324051")
    assert isbn_checksum_ok("0306406152") and not isbn_checksum_ok("0306406153")


def test_url_volume_numbers():
    assert url_volume_numbers("https://www.gerekliseyler.com.tr/urun/happiness-5", set()) == {5}
    # Kitapseç: trailing product id is not a volume.
    assert url_volume_numbers("https://www.kitapsec.com/Products/Death-Note-Olum-Defteri-1-Akil-Celen-Kitaplar-438115.html", set()) == {1}
    # Numbers from the series title and paper type are ignored.
    assert url_volume_numbers("https://x.com/urun/kaiju-no-8-8-nolu-canavar-9", {8}) == {9}
    assert url_volume_numbers("https://x.com/solo-leveling-cilt-2-2-hamur-ana-kapak", set()) == {2}
    # No slug (Bora style) -> nothing to compare.
    assert url_volume_numbers("https://boradagitim.com/Istem/Urun/Detay.aspx?Id=143400", set()) == set()


def _listing(db, volume, store, url, price, in_stock=True):
    db.add(StoreListing(volume_id=volume.id, store_id=store.id, product_url=url, price=price,
                        in_stock=in_stock, last_checked=datetime.now(timezone.utc)))


def test_health_report_flags_each_case(client, db_session, monkeypatch):
    happiness = seed_catalog_series(db_session, "Happiness", "Kayıp Kıta", volumes=(4, 5, 6))
    skip = seed_catalog_series(db_session, "Skip and Loafer", "Kayıp Kıta", volumes=(1, 2, 3, 4, 5))
    vols = {v.volume_number: v for v in db_session.scalars(select(Volume).where(Volume.series_id == happiness.id))}
    skips = {v.volume_number: v for v in db_session.scalars(select(Volume).where(Volume.series_id == skip.id))}
    for v in [*vols.values(), *skips.values()]:
        v.catalog_present = v.catalog_released = True
    vols[5].isbn = HAPPINESS_5
    skips[1].isbn = "9786259324051"  # bad check digit
    stores = [Store(code=f"s{i}", name=f"Mağaza {i}") for i in range(4)]
    db_session.add_all(stores)
    db_session.flush()
    # Cilt 6 has no ISBN; one store's product URL says it is Cilt 5.
    _listing(db_session, vols[6], stores[0], "https://a.example/urun/happiness-5", 29000)
    # Cilt 4: one store far above the others.
    for store, price in zip(stores, (20000, 21000, 20500, 60000)):
        _listing(db_session, vols[4], store, f"https://{store.code}.example/happiness-4", price)
    # Skip and Loafer 5 priced like a limited edition next to 200 TL volumes.
    for n, price in ((1, 20000), (2, 20000), (3, 21000), (4, 20000), (5, 90000)):
        _listing(db_session, skips[n], stores[1], f"https://b.example/skip-and-loafer-{n}", price)
    db_session.commit()
    monkeypatch.setattr(catalog_state, "read_state", lambda: {"last": {"finished_at": "2026-10-17T00:00:00", "isbn_candidates": [
        {"volume_id": vols[6].id, "current_isbn": None, "source_isbn": HAPPINESS_5, "source_url": "https://mangakol.com/x"},
        {"volume_id": skips[4].id, "current_isbn": None, "source_isbn": SKIP_4, "source_url": "https://mangakol.com/y"},
    ]}})
    listings_before = db_session.scalar(select(func.count()).select_from(StoreListing))

    response = client.get("/admin/isbn/health")
    assert response.status_code == 200
    report = response.json()
    checks = report["checks"]

    assert report["totals"]["released_without_isbn"] == 6
    assert report["totals"]["without_isbn_but_listed"] == 6
    assert checks["off_by_one"]["count"] == 1
    shifted = checks["off_by_one"]["items"][0]
    assert shifted["volume_number"] == 6 and shifted["holder"]["volume_number"] == 5
    assert [(r["volume_number"], r["kind"]) for r in checks["deferred_catalog_isbn"]["items"]] == [(4, "safe_to_write")]
    mismatch = checks["url_volume_mismatch"]["items"]
    assert [(r["series"], r["volume_number"], r["url_number"]) for r in mismatch] == [("Happiness", 6, 5)]
    outlier = checks["listing_price_outlier"]["items"]
    assert len(outlier) == 1 and outlier[0]["price"] == 600.0 and outlier[0]["volume_number"] == 4
    assert [(r["series"], r["volume_number"]) for r in checks["volume_price_outlier"]["items"]] == [("Skip and Loafer", 5)]
    assert [(r["volume_number"], r["problem"]) for r in checks["invalid_isbn"]["items"]] == [(1, "checksum")]

    # Read-only: no ISBN written, no listing touched.
    db_session.expire_all()
    assert db_session.get(Volume, vols[6].id).isbn is None
    assert db_session.get(Volume, skips[4].id).isbn is None
    assert db_session.scalar(select(func.count()).select_from(StoreListing)) == listings_before


def test_health_report_requires_admin(client):
    client.cookies.clear()
    assert client.get("/admin/isbn/health").status_code == 401
