from datetime import date

from sqlalchemy import select

from app.models import Volume
from app.scrapers.mangakol import CatalogVolumeDetails
from app.services.catalog_sync import CatalogSyncService
from app.utils import utcnow
from tests.test_catalog_isbn import _DetailsFake, _vol, _zom
from tests.test_catalog_sync import FakeMangakolScraper


def test_new_release_refreshes_recent_missing_details(db_session):
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([_zom([_vol(1, released=False)])])).sync()
    vol = db_session.scalar(select(Volume))
    vol.details_checked_at = utcnow()
    db_session.commit()
    cv = _vol(1)
    fake = _DetailsFake([_zom([cv])], {cv.url: CatalogVolumeDetails("9786257646628", 192, date(2026, 10, 13))})
    CatalogSyncService(db_session, scraper=fake).sync()
    assert fake.fetched == [cv.url]
    assert (vol.isbn, vol.page_count, vol.release_date) == ("9786257646628", 192, date(2026, 10, 13))


def test_conflicting_source_does_not_overwrite_existing_metadata(db_session):
    cv = _vol(1)
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([_zom([cv])])).sync()
    vol = db_session.scalar(select(Volume))
    vol.isbn, vol.page_count, vol.release_date = "9786257646628", 192, date(2021, 3, 1)
    db_session.commit()
    fake = _DetailsFake([_zom([cv])], {cv.url: CatalogVolumeDetails("9786257646642", 222, date(2026, 10, 13))})
    report = CatalogSyncService(db_session, scraper=fake).sync()
    assert report.isbn_conflicts == 1
    assert (vol.isbn, vol.page_count, vol.release_date) == ("9786257646628", 192, date(2021, 3, 1))


def test_matching_source_only_fills_empty_fields(db_session):
    cv = _vol(1)
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([_zom([cv])])).sync()
    vol = db_session.scalar(select(Volume))
    vol.isbn, vol.page_count = "9786257646628", 192
    db_session.commit()
    fake = _DetailsFake([_zom([cv])], {cv.url: CatalogVolumeDetails("9786257646628", 222, date(2026, 10, 13))})
    CatalogSyncService(db_session, scraper=fake).sync()
    assert (vol.page_count, vol.release_date) == (192, date(2026, 10, 13))


def test_variant_cannot_claim_another_volume_number_isbn(db_session):
    from dataclasses import replace
    from tests.test_catalog_variants import BASE, REGULAR, _Fake, _soichi, _volume
    manga = _soichi()
    CatalogSyncService(db_session, scraper=_Fake([manga])).sync()
    variant = _volume(db_session, "Soichi (Bez Cilt)")
    variant.isbn = None
    variant.volume_number = 4
    variant.details_checked_at = None
    manga.variants[0].volumes[0] = replace(manga.variants[0].volumes[0], number=4)
    db_session.commit()
    fake = _DetailsFake([manga], {
        f"{BASE}/cilt-1": CatalogVolumeDetails(REGULAR),
        f"{BASE}/cilt-1-clothbound": CatalogVolumeDetails(REGULAR, 200, date(2026, 10, 13)),
    })
    report = CatalogSyncService(db_session, scraper=fake).sync()
    assert report.isbn_conflicts == 1
    assert _volume(db_session, "Soichi").isbn == REGULAR
    assert variant.isbn is None and variant.page_count is None and variant.release_date is None
