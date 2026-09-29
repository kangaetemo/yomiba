"""Catalog ISBNs from Mangakol volume pages.

Mangakol prints each released volume's ISBN on its own page (live-checked
2026-09-29: Dragon Ball "Cilt 5" = 9786258237337, the same ISBN BKM sends
for "Dragon Ball 9&10"). With catalog ISBNs the importer's ISBN-first step
matches store products whatever their title says.
"""

from __future__ import annotations

import httpx
import pytest
from bs4 import BeautifulSoup
from sqlalchemy import select

from app.config import get_settings
from app.models import Series, StoreListing, Volume
from app.scrapers.mangakol import CatalogManga, CatalogVolume, MangakolCatalogScraper
from app.services.catalog_sync import CatalogSyncService
from app.services.import_service import ImportAction
from tests.test_catalog_sync import FakeMangakolScraper
from tests.test_import_service import make_result, seed_catalog_series

BASE = "https://mangakol.com"


def test_volume_item_reads_page_url_and_release_state():
    html = """
    <div class="mk-vol-item" data-binding-format="SingleVolume">
      <a class="mk-vol-card-link" href="/manga/zom-100/cilt-9"></a>
      <button data-volume-number="9"></button><span>12 Mar 2025</span>
    </div>
    <div class="mk-vol-item" data-binding-format="SingleVolume">
      <a class="mk-vol-card-link" href="/manga/zom-100/cilt-11"></a>
      <button data-volume-number="11"></button><span>Yakında</span>
    </div>"""
    vols = MangakolCatalogScraper._volume_items(BeautifulSoup(html, "lxml"))
    assert [(v.number, v.url, v.released) for v in vols] == [
        (9, f"{BASE}/manga/zom-100/cilt-9", True),
        (11, f"{BASE}/manga/zom-100/cilt-11", False),
    ]


def _mangakol(pages: dict[str, str]) -> MangakolCatalogScraper:
    def handler(request: httpx.Request) -> httpx.Response:
        body = pages.get(str(request.url))
        return httpx.Response(200, text=body) if body is not None else httpx.Response(404)

    scraper = MangakolCatalogScraper(client=httpx.Client(transport=httpx.MockTransport(handler)))
    scraper._throttle = lambda: None  # noqa: SLF001 - no delays in tests
    return scraper


def test_fetch_volume_isbn_reads_info_row():
    url = f"{BASE}/manga/dragon-ball/cilt-5-2in1"
    page = ('<span><strong class="text-secondary">Sayfa Sayısı:</strong> 388</span> '
            '<span><strong class="text-secondary">ISBN:</strong> 9786258237337</span>')
    scraper = _mangakol({url: page, f"{BASE}/none": "<html>no isbn row</html>"})
    assert scraper.fetch_volume_isbn(url) == "9786258237337"
    assert scraper.fetch_volume_isbn(f"{BASE}/none") is None
    assert scraper.fetch_volume_isbn(f"{BASE}/missing") is None  # 404


class _IsbnFake(FakeMangakolScraper):
    def __init__(self, manga, isbns: dict[str, str]):
        super().__init__(manga)
        self.isbns = isbns
        self.fetched: list[str] = []

    def fetch_volume_isbn(self, url: str) -> str | None:
        self.fetched.append(url)
        return self.isbns.get(url)


def _vol(n, released=True):
    return CatalogVolume(number=n, cover_url=None, url=f"{BASE}/manga/zom-100/cilt-{n}",
                         released=released)


def _zom(volumes):
    return CatalogManga(slug="zom-100", title="Zom 100: Ölülerin Yapılacaklar Listesi",
                        local_publisher="Marmara Çizgi", volumes=volumes)


def _isbns(db_session) -> dict[int, str | None]:
    return {v.volume_number: v.isbn for v in db_session.scalars(select(Volume))}


def test_sync_backfills_isbns_of_released_volumes(db_session):
    fake = _IsbnFake([_zom([_vol(1), _vol(2), _vol(3, released=False)])], {
        f"{BASE}/manga/zom-100/cilt-1": "9786257646628",
        f"{BASE}/manga/zom-100/cilt-2": "9786257646642",
    })
    report = CatalogSyncService(db_session, scraper=fake).sync()

    assert _isbns(db_session) == {1: "9786257646628", 2: "9786257646642", 3: None}
    assert f"{BASE}/manga/zom-100/cilt-3" not in fake.fetched  # "Yakında": never asked
    assert (report.isbn_pages, report.isbns_added, report.isbn_conflicts) == (2, 2, 0)

    # next sync: volumes that already have an ISBN are not fetched again
    fake.fetched.clear()
    CatalogSyncService(db_session, scraper=fake).sync()
    assert fake.fetched == []


def test_sync_isbn_budget_spreads_over_syncs(db_session, monkeypatch):
    from dataclasses import replace

    one = replace(get_settings(), mangakol_max_isbn_requests=1)
    monkeypatch.setattr("app.services.catalog_sync.get_settings", lambda: one)
    fake = _IsbnFake([_zom([_vol(1), _vol(2)])], {
        f"{BASE}/manga/zom-100/cilt-1": "9786257646628",
        f"{BASE}/manga/zom-100/cilt-2": "9786257646642",
    })
    CatalogSyncService(db_session, scraper=fake).sync()
    assert _isbns(db_session) == {1: "9786257646628", 2: None}
    CatalogSyncService(db_session, scraper=fake).sync()
    assert _isbns(db_session) == {1: "9786257646628", 2: "9786257646642"}


def test_isbn_held_by_another_volume_is_reported_not_moved(db_session):
    other = seed_catalog_series(db_session, "Başka Seri", "Marmara Çizgi", volumes=(4,))
    held = db_session.scalar(select(Volume).where(Volume.series_id == other.id))
    held.isbn = "9786257646628"
    db_session.commit()

    fake = _IsbnFake([_zom([_vol(1)])], {f"{BASE}/manga/zom-100/cilt-1": "9786257646628"})
    report = CatalogSyncService(db_session, scraper=fake).sync()

    zom = db_session.scalar(select(Series).where(Series.title.like("Zom 100%")))
    zom_vol = db_session.scalar(select(Volume).where(Volume.series_id == zom.id))
    assert zom_vol.isbn is None
    assert held.isbn == "9786257646628"
    assert report.isbn_conflicts == 1
    assert "Başka Seri Cilt 4" in report.isbn_conflict_details[0]
    # a conflict is a data finding, not a sync error
    assert not any("ISBN" in e for e in report.errors)


def test_catalog_isbn_matches_store_title_the_catalog_does_not_know(db_session, import_service):
    """Tokyo İntikamcıları: BKM sells "Tokyo Revengers 5. Cilt". With the
    catalog ISBN the title no longer matters."""
    series = seed_catalog_series(db_session, "Tokyo İntikamcıları", "Gerekli Şeyler",
                                 volumes=range(1, 19))
    vol5 = db_session.scalar(select(Volume).where(Volume.series_id == series.id,
                                                  Volume.volume_number == 5))
    vol5.isbn = "9786258237115"
    db_session.commit()

    r = make_result("bkm", "Tokyo Revengers 5. Cilt", "150", isbn="9786258237115",
                    publisher="Gerekli Şeyler Yayıncılık")
    assert import_service.import_result(r) == ImportAction.CREATED
    db_session.commit()
    assert db_session.scalar(select(StoreListing)).volume_id == vol5.id


def test_catalog_isbn_rejects_other_printing_by_title(db_session, import_service):
    """A product whose ISBN differs from the catalog volume's is another
    edition: the title match must not attach it."""
    series = seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1,))
    vol = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    vol.isbn = "9786256335424"
    db_session.commit()

    r = make_result("bkm", "Berserk 1", "150", isbn="9789750000001",
                    publisher="Athica Yayınları")
    assert import_service.import_result(r) == ImportAction.SKIPPED
    assert import_service.last_reason == "isbn_conflict"


# -- legacy "Cilt -1" rows holding the catalog ISBN -------------------------------------

def _look_back(isbn_map):
    manga = CatalogManga(slug="look-back", title="Look Back", local_publisher="Gerekli Şeyler",
                         volumes=[CatalogVolume(number=1, cover_url=None,
                                                url=f"{BASE}/manga/look-back/cilt-1")])
    return _IsbnFake([manga], isbn_map)


def _phantom_with_listing(db_session, isbn):
    from app.models import PriceHistory, Store

    # series + Cilt 1 exist before the ISBN work (a plain catalog sync)
    CatalogSyncService(db_session, scraper=FakeMangakolScraper(_look_back({})._manga)).sync()
    series = db_session.scalar(select(Series).where(Series.title == "Look Back"))
    phantom = Volume(series_id=series.id, volume_number=-1, isbn=isbn)
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add_all([phantom, store])
    db_session.flush()
    listing = StoreListing(volume_id=phantom.id, store_id=store.id,
                           product_url="https://bkm.example/look-back", price=15000)
    db_session.add(listing)
    db_session.flush()
    db_session.add(PriceHistory(listing_id=listing.id, price=15000))
    db_session.commit()
    return series, phantom.id, listing.id


def test_same_series_legacy_row_is_merged_into_catalog_volume(db_session):
    from app.models import PriceHistory

    isbn = "9786256031302"
    series, phantom_id, listing_id = _phantom_with_listing(db_session, isbn)

    report = CatalogSyncService(db_session, scraper=_look_back(
        {f"{BASE}/manga/look-back/cilt-1": isbn})).sync()

    vol1 = db_session.scalar(select(Volume).where(Volume.series_id == series.id,
                                                  Volume.volume_number == 1))
    assert vol1.isbn == isbn
    assert db_session.get(Volume, phantom_id) is None
    listing = db_session.get(StoreListing, listing_id)
    assert listing.volume_id == vol1.id  # the offer moved with its history
    assert db_session.scalar(select(PriceHistory.listing_id)) == listing_id
    assert (report.isbn_phantoms_merged, report.isbn_conflicts, report.isbns_added) == (1, 0, 1)


def test_legacy_row_with_personal_data_is_only_reported(db_session):
    from app.models import User, UserVolumeCollection

    isbn = "9786256031302"
    series, phantom_id, _ = _phantom_with_listing(db_session, isbn)
    user = User(email="u@example.com", display_name="U")
    db_session.add(user)
    db_session.flush()
    db_session.add(UserVolumeCollection(user_id=user.id, volume_id=phantom_id, status="owned"))
    db_session.commit()

    report = CatalogSyncService(db_session, scraper=_look_back(
        {f"{BASE}/manga/look-back/cilt-1": isbn})).sync()

    assert db_session.get(Volume, phantom_id) is not None
    assert report.isbn_phantoms_merged == 0
    assert report.isbn_conflicts == 1
    assert "elle birleştirilmeli" in report.isbn_conflict_details[0]


# -- volume details: page count, local release date, credits -----------------------------

def test_fetch_volume_details_reads_info_rows():
    from datetime import date

    url = f"{BASE}/manga/dragon-ball/cilt-5-2in1"
    page = ('<span><strong class="text-secondary">Sayfa Sayısı:</strong> 388</span> '
            '<span><strong class="text-secondary">ISBN:</strong> 9786258237337</span> '
            '<span><strong class="text-secondary">Yayın Tarihi (Orijinal):</strong> 10 Eylül 1987</span> '
            '<span><strong class="text-secondary">Yayın Tarihi (Yerel):</strong> 22 Haziran 2023</span>')
    details = _mangakol({url: page}).fetch_volume_details(url)
    assert (details.isbn, details.page_count, details.release_date) == (
        "9786258237337", 388, date(2023, 6, 22))


@pytest.mark.parametrize("raw,expected", [
    ("22 Haziran 2023", (2023, 6, 22)), ("1 Şubat 2021", (2021, 2, 1)),
    ("10 Ağustos 2024", (2024, 8, 10)), ("Yakında", None), ("", None), ("31 Şubat 2021", None),
])
def test_parse_tr_date(raw, expected):
    from datetime import date

    from app.scrapers.mangakol import parse_tr_date

    assert parse_tr_date(raw) == (date(*expected) if expected else None)


class _DetailsFake(FakeMangakolScraper):
    def __init__(self, manga, details):
        super().__init__(manga)
        self.details = details
        self.fetched: list[str] = []

    def fetch_volume_details(self, url):
        self.fetched.append(url)
        return self.details.get(url)


def test_sync_stores_details_and_reads_each_page_once(db_session):
    from datetime import date

    from app.scrapers.mangakol import CatalogVolumeDetails

    manga = CatalogManga(slug="zom-100", title="Zom 100", local_publisher="Marmara Çizgi",
                         volumes=[_vol(1)], author="Haro Aso", illustrator="Kotaro Takata")
    url = f"{BASE}/manga/zom-100/cilt-1"
    fake = _DetailsFake([manga], {url: CatalogVolumeDetails("9786257646628", 192, date(2021, 3, 1))})
    CatalogSyncService(db_session, scraper=fake).sync()

    vol = db_session.scalar(select(Volume))
    assert (vol.isbn, vol.page_count, vol.release_date) == ("9786257646628", 192, date(2021, 3, 1))
    assert vol.details_checked_at is not None
    series = db_session.scalar(select(Series))
    assert (series.author, series.illustrator) == ("Haro Aso", "Kotaro Takata")

    fake.fetched.clear()
    CatalogSyncService(db_session, scraper=fake).sync()
    assert fake.fetched == []


def test_volume_with_isbn_but_no_details_is_read_once_for_details(db_session):
    """Rows that got their ISBN before details existed are read one more time."""
    from datetime import date

    from app.scrapers.mangakol import CatalogVolumeDetails

    url = f"{BASE}/manga/zom-100/cilt-1"
    fake = _DetailsFake([_zom([_vol(1)])], {url: CatalogVolumeDetails("9786257646628", 192, date(2021, 3, 1))})
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([_zom([_vol(1)])])).sync()
    vol = db_session.scalar(select(Volume))
    vol.isbn = "9786257646628"  # filled by the earlier ISBN-only sync
    db_session.commit()

    CatalogSyncService(db_session, scraper=fake).sync()
    assert fake.fetched == [url]
    assert (vol.page_count, vol.release_date) == (192, date(2021, 3, 1))
