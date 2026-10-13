from copy import deepcopy

from app.scrapers.mangakol import CatalogManga, CatalogVolume, CatalogVariant, CatalogVolumeDetails
from app.services.catalog_audit import audit, snapshot
from tests.test_catalog_sync import FakeMangakolScraper
from tests.test_import_service import seed_catalog_series


def seed(session, volumes):
    from sqlalchemy import select
    from app.models import CatalogSeries
    series = seed_catalog_series(session, "Fairy Tail", "Gerekli Şeyler", volumes=volumes)
    session.scalar(select(CatalogSeries).where(CatalogSeries.series_id == series.id)).mangakol_slug = "fairy-tail"
    session.commit()
    return series


def source(*, complete=True):
    return CatalogManga(slug="fairy-tail", title="Fairy Tail", local_publisher="Gerekli Şeyler",
                        volumes=[CatalogVolume(number=1, cover_url=None),
                                 CatalogVolume(number=2, cover_url=None, released=False)],
                        volumes_complete=complete)


def test_report_detects_extra_and_announced_without_writing(db_session):
    seed(db_session, (1, 2, 63))
    before = snapshot(db_session)
    db = deepcopy(before)
    result = audit(db, FakeMangakolScraper([source()]))
    assert result["complete"] and not result["applied"]
    assert result["counts"]["extra_volume"] == 1
    assert result["counts"]["announced_visible"] == 1
    assert [d["number"] for d in result["differences"] if d["kind"] == "extra_volume"] == [63]
    assert db == before
    assert snapshot(db_session)["series"] == before["series"]
    assert set(db["series"][0]) == {"id", "title", "publisher", "slugs", "volumes"}


def test_partial_source_cannot_claim_extra_volumes(db_session):
    seed(db_session, (1, 2, 63))
    result = audit(snapshot(db_session), FakeMangakolScraper([source(complete=False)]))
    assert not result["complete"]
    assert not result["counts"].get("extra_volume")


def test_partial_catalog_cannot_claim_stale_series(db_session):
    seed(db_session, (1,))
    seed_catalog_series(db_session, "Other", "Gerekli Şeyler", volumes=(1,))
    scraper = FakeMangakolScraper([source()])
    scraper.catalog_list_complete = False
    result = audit(snapshot(db_session), scraper)
    assert not result["complete"]
    assert not result["counts"].get("stale_series")


def test_variants_are_separate_and_hidden_rows_are_retained(db_session):
    seed(db_session, (1, 2))
    db = snapshot(db_session)
    db["series"][0]["volumes"].append({"id": 99, "number": 63, "isbn": None, "public": False,
                                     "catalog_released": False, "release_date": None})
    manga = source()
    from dataclasses import replace
    manga = replace(manga, variants=(CatalogVariant("Clothbound", "Bez Cilt", [CatalogVolume(1, None)]),))
    result = audit(db, FakeMangakolScraper([manga]))
    assert result["counts"]["retained_hidden_volume"] == 1
    assert any(d["slug"] == "fairy-tail~clothbound" and d["kind"] == "missing_series"
               for d in result["differences"])


def test_metadata_difference_and_source_failure_are_explicit(db_session):
    seed(db_session, (1, 2))
    scraper = FakeMangakolScraper([source()])
    from dataclasses import replace
    scraper._manga = [replace(source(), volumes=[CatalogVolume(1, None, url="https://mangakol.com/example")])]
    scraper.fetch_volume_details = lambda url: CatalogVolumeDetails(isbn="9786255606402")
    result = audit(snapshot(db_session), scraper, details=True)
    assert result["details_checked"] == 1
    assert result["counts"]["isbn_difference"] == 1
    failed = audit(snapshot(db_session), FakeMangakolScraper([source()], {"fairy-tail"}))
    assert not failed["complete"] and failed["errors"]


def test_audit_routes_require_admin(client):
    client.cookies.clear()
    assert client.get("/catalog/audit/snapshot").status_code == 401
    assert client.get("/catalog/audit/report").status_code == 401
    assert client.post("/catalog/audit").status_code == 401


def test_admin_can_run_and_download_fixed_snapshot(client, engine, monkeypatch):
    from sqlalchemy.orm import sessionmaker
    from app.routes import catalog
    from app.services import catalog_audit as audit_module
    monkeypatch.setattr(catalog, "SessionLocal", sessionmaker(bind=engine))
    monkeypatch.setattr(audit_module,
                        "audit", lambda db, **kwargs: {"complete": True, "applied": False,
                                                      "db_snapshot": db, "counts": {}})
    class InlineThread:
        def __init__(self, *, target, args, **kwargs):
            self.target, self.args = target, args
        def start(self):
            self.target(*self.args)
    monkeypatch.setattr(catalog.threading, "Thread", InlineThread)
    assert client.get("/catalog/audit/snapshot").json()["series"] == []
    assert client.post("/catalog/audit?details=true").status_code == 202
    assert client.get("/catalog/audit/status").json()["last"]["complete"]
    report = client.get("/catalog/audit/report").json()
    assert report["db_snapshot"]["series"] == [] and report["applied"] is False
    monkeypatch.setattr(catalog, "_audit_running", True)
    assert client.post("/catalog/audit").status_code == 409
