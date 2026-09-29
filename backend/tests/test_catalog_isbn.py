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
