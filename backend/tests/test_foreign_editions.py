"""Foreign editions: rejected by the importer, replaced by the catalog sync,
and old ones cleaned up by the admin scan.

Real case (2026-09-30): "Naruto Cilt 11" carried VIZ's English ISBN
9781421502410 and a Kitapbulan listing of the English book.
"""

from __future__ import annotations

import json
import time

from sqlalchemy import select

from app.models import CatalogSeries, ListingExclusion, Series, Store, StoreListing, Volume
from app.scrapers.mangakol import CatalogManga, CatalogVolume, CatalogVolumeDetails
from app.services.catalog_sync import CatalogSyncService
from app.services.foreign_editions import apply_plan, build_plan
from app.services.import_service import ImportAction
from tests.test_catalog_sync import FakeMangakolScraper
from tests.test_import_service import make_result, seed_catalog_series

VIZ = "9781421502410"
GS_11 = "9786257590525"


def _page(isbn=None, language=None):
    node = {"@context": "https://schema.org", "@type": "Book"}
    if isbn:
        node["isbn"] = isbn
    if language:
        node["inLanguage"] = language
    return f'<script type="application/ld+json">{json.dumps(node)}</script>'


def test_importer_rejects_foreign_isbn_and_language(db_session, import_service):
    seed_catalog_series(db_session, "Naruto", "Gerekli Şeyler", volumes=(11,))
    english = make_result("bkm", "Naruto 11", "300", isbn=VIZ, publisher="Gerekli Şeyler Yayıncılık")
    assert import_service.import_result(english) == ImportAction.SKIPPED
    assert import_service.last_reason == "foreign_edition"

    tagged = make_result("bkm", "Naruto 11", "300", publisher="Gerekli Şeyler Yayıncılık")
    tagged = tagged.model_copy(update={"language": "English"})
    assert import_service.import_result(tagged) == ImportAction.SKIPPED
    assert import_service.last_reason == "foreign_edition"


def test_catalog_sync_replaces_foreign_volume_isbn(db_session):
    manga = CatalogManga(slug="naruto", title="Naruto", local_publisher="Gerekli Şeyler",
                         volumes=[CatalogVolume(number=11, cover_url=None, url="https://mangakol.com/manga/naruto/cilt-11")])

    class Fake(FakeMangakolScraper):
        def fetch_volume_details(self, url):
            return CatalogVolumeDetails(isbn=GS_11)

    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    vol = db_session.scalar(select(Volume))
    vol.isbn = VIZ  # left behind by an old title match
    db_session.commit()

    CatalogSyncService(db_session, scraper=Fake([manga])).sync()
    assert vol.isbn == GS_11


def _naruto_with_listings(db_session):
    series = seed_catalog_series(db_session, "Naruto", "Gerekli Şeyler", volumes=(10, 11))
    v10, v11 = db_session.scalars(select(Volume).where(Volume.series_id == series.id).order_by(Volume.volume_number)).all()
    v10.isbn, v11.isbn = "9786257590518", VIZ
    kb, bkm = Store(code="kitapbulan", name="Kitapbulan"), Store(code="bkm", name="BKM")
    db_session.add_all([kb, bkm])
    db_session.flush()
    rows = {
        "kb11": StoreListing(volume_id=v11.id, store_id=kb.id, product_url="https://kb/naruto-11", price=1),
        "bkm11": StoreListing(volume_id=v11.id, store_id=bkm.id, product_url="https://bkm/naruto-11", price=1),
        "kb10": StoreListing(volume_id=v10.id, store_id=kb.id, product_url="https://kb/naruto-10", price=1),
    }
    db_session.add_all(rows.values())
    db_session.commit()
    return v10, v11, rows


def test_scan_and_apply_remove_only_proven_foreign_listings(db_session):
    v10, v11, rows = _naruto_with_listings(db_session)
    pages = {
        "https://kb/naruto-11": _page(VIZ, "en"),               # the English book
        "https://bkm/naruto-11": _page(GS_11, "tr"),            # the real Turkish volume
        "https://kb/naruto-10": _page(None, "English"),         # English import, no ISBN
    }
    plan = build_plan(db_session, pages.get)
    actions = {(l["store"], l["volume_number"]): l["action"] for l in plan["listings"]}
    assert actions == {("kitapbulan", 11): "remove", ("bkm", 11): "keep", ("kitapbulan", 10): "remove"}
    assert [v["isbn"] for v in plan["foreign_isbn_volumes"]] == [VIZ]

    result = apply_plan(db_session, plan)
    assert result == {"removed_listings": 2, "cleared_isbns": 1, "backup": None}
    assert db_session.get(StoreListing, rows["bkm11"].id) is not None
    assert v11.isbn is None and v11.details_checked_at is None
    assert {e.product_url for e in db_session.scalars(select(ListingExclusion))} == {
        "https://kb/naruto-11", "https://kb/naruto-10"}


def test_admin_scan_endpoint_runs_in_background(client, db_session, monkeypatch):
    from app.services import isbn_conflict_fix

    _naruto_with_listings(db_session)
    monkeypatch.setattr(isbn_conflict_fix, "default_fetch", lambda: {"https://kb/naruto-11": _page(VIZ)}.get)
    assert client.post("/catalog/foreign-editions/scan").status_code == 202
    for _ in range(100):
        status = client.get("/catalog/foreign-editions").json()
        if status["state"] == "ready":
            break
        time.sleep(0.05)
    assert status["state"] == "ready"
    res = client.post("/catalog/foreign-editions/apply")
    assert res.status_code == 200 and res.json()["removed_listings"] == 1
    assert client.post("/catalog/foreign-editions/apply").status_code == 409  # plan consumed


# -- products the store removed (BKM keeps them in search with an old price) -----

def test_bkm_drops_out_of_stock_products_whose_page_is_gone():
    import httpx

    from app.scrapers.bkm import BkmScraper
    from app.scrapers.search_result import SearchResult

    pages = {"https://www.bkmkitap.com/one-piece-48": 404, "https://www.bkmkitap.com/one-piece-49": 200}
    client = httpx.Client(transport=httpx.MockTransport(
        lambda req: httpx.Response(pages.get(str(req.url), 200), text="x")))
    scraper = BkmScraper(client=client)
    scraper._throttle = lambda: None
    scraper.stats = {"rejected": {}}
    scraper.gone_urls, scraper._page_checked = set(), set()

    def result(n, in_stock):
        return SearchResult(store_id="bkm", store_name="BKM Kitap", title=f"One Piece {n}. Cilt",
                            product_url=f"https://www.bkmkitap.com/one-piece-{n}", in_stock=in_stock)

    kept = scraper._drop_gone([result(48, False), result(49, False), result(50, True)])
    assert [r.title for r in kept] == ["One Piece 49. Cilt", "One Piece 50. Cilt"]
    assert scraper.gone_urls == {"https://www.bkmkitap.com/one-piece-48"}


def test_import_deletes_listing_of_a_removed_product(db_session):
    from app.services.import_service import ImportService
    from tests.helpers import RecordingScraper

    series = seed_catalog_series(db_session, "One Piece", "Gerekli Şeyler", volumes=(48,))
    vol = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add(store)
    db_session.flush()
    ghost = StoreListing(volume_id=vol.id, store_id=store.id, price=12750, in_stock=False,
                         product_url="https://www.bkmkitap.com/one-piece-48")
    db_session.add(ghost)
    db_session.commit()

    class GoneScraper(RecordingScraper):
        def search(self, query):
            self.gone_urls = {"https://www.bkmkitap.com/one-piece-48"}
            return []

    report = ImportService(db_session, scrapers=[GoneScraper(store_id="bkm")]).run_import("One Piece")
    assert db_session.get(StoreListing, ghost.id) is None
    assert report.stores[0].reasons["gone"] == 1


# -- follow-ups: store barcodes, English wording, "Box"/"Kutu" in titles ------------

def test_store_barcode_is_not_an_isbn():
    from app.normalization.isbn import book_isbn, is_foreign_isbn

    assert book_isbn("9693110002326") is None          # Kitapseç "Trace 3" stock code
    assert is_foreign_isbn("9693110002326") is False    # unknown, not foreign
    assert book_isbn("9786259400532") == "9786259400532"


def test_barcode_never_becomes_a_volume_isbn(db_session, import_service):
    series = seed_catalog_series(db_session, "Trace", "Athica", volumes=(3,))
    r = make_result("bkm", "Trace 3", "100", isbn="9693110002326", publisher="Athica Yayınları")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert db_session.scalar(select(Volume.isbn).where(Volume.series_id == series.id)) is None


def test_english_wording_and_publishers_are_rejected(db_session, import_service):
    seed_catalog_series(db_session, "Boruto", "Gerekli Şeyler", volumes=(5,))
    viz = make_result("bkm", "Boruto 5 Viz Media", "300")
    assert import_service.import_result(viz) == ImportAction.SKIPPED
    assert import_service.last_reason == "foreign_edition"
    no_pub = make_result("bkm", "Boruto, Vol. 5", "300")
    assert import_service.import_result(no_pub) == ImportAction.SKIPPED
    assert import_service.last_reason == "foreign_edition"
    # a named publisher or a Turkish ISBN keeps the regular rules
    tr = make_result("bkm", "Boruto Vol 5", "150", publisher="Gerekli Şeyler Yayıncılık")
    assert import_service.import_result(tr) == ImportAction.CREATED


def test_blue_box_mavi_kutu_is_a_volume_not_a_box(db_session, import_service):
    """Every store dropped "Blue Box – Mavi Kutu N" as a box set ("Box",
    "Kutu"); the series never got a price."""
    from app.normalization import parse_volume_title

    assert parse_volume_title("Blue Box – Mavi Kutu 4").is_collection is False
    assert parse_volume_title("Berserk Box").is_collection is True
    assert parse_volume_title("One Piece Kutu Seti").is_collection is True
    series = seed_catalog_series(db_session, "Mavi Kutu", "Akılçelen", volumes=range(1, 6))
    r = make_result("bkm", "Blue Box – Mavi Kutu 4", "150", publisher="Akıl Çelen Kitaplar")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert db_session.scalar(select(StoreListing)).volume.volume_number == 4
