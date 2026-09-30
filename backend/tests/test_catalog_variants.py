"""Binding variants: Mangakol lists e.g. Soichi's "Bez Cilt" (Clothbound)
edition in its own detail-page tab. Each variant is its own catalog series
("Soichi (Bez Cilt)", manifest slug "<slug>~clothbound"); stores title both
bindings plainly "Soichi", so the ISBN decides where a product goes."""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select

from app.models import CatalogSeries, Series, Store, StoreListing, Volume
from app.scrapers.mangakol import CatalogManga, CatalogVariant, CatalogVolume
from app.scrapers.search_result import SearchResult
from app.services.background_import import fallback_queries
from app.services.catalog_sync import CatalogSyncService
from app.services.import_service import ImportService
from tests.test_catalog_sync import FakeMangakolScraper
from tests.test_import_service import _fake_scrapers

BASE = "https://mangakol.com/manga/souichi-no-katte-na-noroi"
REGULAR, CLOTH = "9786259031101", "9786259031118"


class _Fake(FakeMangakolScraper):
    def fetch_volume_details(self, url):
        from app.scrapers.mangakol import CatalogVolumeDetails

        return CatalogVolumeDetails(isbn={f"{BASE}/cilt-1": REGULAR, f"{BASE}/cilt-1-clothbound": CLOTH}.get(url))


def _soichi(with_variant: bool = True) -> CatalogManga:
    variants = (CatalogVariant("Clothbound", "Bez Cilt", [
        CatalogVolume(number=1, cover_url=None, url=f"{BASE}/cilt-1-clothbound"),
    ]),) if with_variant else ()
    return CatalogManga(
        slug="souichi-no-katte-na-noroi", title="Soichi", local_publisher="Kayıp Kıta",
        volumes=[CatalogVolume(number=1, cover_url=None, url=f"{BASE}/cilt-1")],
        author="Junji Ito", variants=variants,
    )


def _volume(db_session, title) -> Volume:
    series = db_session.scalar(select(Series).where(Series.title == title))
    return db_session.scalar(select(Volume).where(Volume.series_id == series.id))


def test_sync_creates_variant_series_with_own_isbn(db_session):
    report = CatalogSyncService(db_session, scraper=_Fake([_soichi()])).sync()

    assert report.errors == []
    slugs = dict(db_session.execute(select(CatalogSeries.mangakol_slug, CatalogSeries.series_id)).all())
    assert set(slugs) == {"souichi-no-katte-na-noroi", "souichi-no-katte-na-noroi~clothbound"}
    cloth = db_session.get(Series, slugs["souichi-no-katte-na-noroi~clothbound"])
    regular = db_session.get(Series, slugs["souichi-no-katte-na-noroi"])
    assert cloth.title == "Soichi (Bez Cilt)"
    assert cloth.publisher_id == regular.publisher_id
    assert cloth.author == "Junji Ito"
    assert _volume(db_session, "Soichi").isbn == REGULAR
    assert _volume(db_session, "Soichi (Bez Cilt)").isbn == CLOTH

    # idempotent
    report = CatalogSyncService(db_session, scraper=_Fake([_soichi()])).sync()
    assert report.errors == [] and report.series_created == 0


def test_variant_of_failed_page_is_not_stale(db_session):
    CatalogSyncService(db_session, scraper=_Fake([_soichi()])).sync()
    fake = _Fake([_soichi()], fail_slugs={"souichi-no-katte-na-noroi"})
    report = CatalogSyncService(db_session, scraper=fake).sync()
    assert not any("stale" in e for e in report.errors)


def test_removed_variant_is_reported_stale(db_session):
    CatalogSyncService(db_session, scraper=_Fake([_soichi()])).sync()
    report = CatalogSyncService(db_session, scraper=_Fake([_soichi(with_variant=False)])).sync()
    assert any("souichi-no-katte-na-noroi~clothbound" in e for e in report.errors)


def _result(store, isbn, price, url, in_stock=True):
    return SearchResult(
        store_id=store, store_name="BKM Kitap", title="Soichi", product_url=url,
        series_title="Soichi", volume_number=None, isbn=isbn, publisher="Kayıp Kıta",
        price=Decimal(price), currency="TRY", in_stock=in_stock,
    )


def test_store_products_go_to_their_binding_by_isbn(db_session):
    CatalogSyncService(db_session, scraper=_Fake([_soichi()])).sync()
    regular, cloth = _volume(db_session, "Soichi"), _volume(db_session, "Soichi (Bez Cilt)")

    # Before the catalog knew the Bez Cilt edition, a title match put the
    # clothbound product's price on the regular volume.
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add(store)
    db_session.flush()
    db_session.add(StoreListing(volume_id=regular.id, store_id=store.id,
                                product_url="https://ks.example/soichi-bez", price=55000))
    db_session.commit()

    scrapers = _fake_scrapers({"bkm": [
        _result("bkm", CLOTH, "550", "https://ks.example/soichi-bez"),
        # sold out: the in-stock switch rule alone would keep the wrong product
        _result("bkm", REGULAR, "400", "https://ks.example/soichi", in_stock=False),
    ]}, failing=set())
    ImportService(db_session, scrapers=scrapers).run_import("Soichi")

    listings = {l.volume_id: (l.product_url, l.price) for l in db_session.scalars(select(StoreListing))}
    assert listings == {
        regular.id: ("https://ks.example/soichi", 40000),
        cloth.id: ("https://ks.example/soichi-bez", 55000),
    }


def test_isbn_beats_edition_words_in_title(db_session, import_service):
    """A variant's own book may say "Deluxe" / "Hardcover": its catalog
    ISBN still places it."""
    CatalogSyncService(db_session, scraper=_Fake([_soichi()])).sync()
    cloth = _volume(db_session, "Soichi (Bez Cilt)")
    result = _result("bkm", CLOTH, "550", "https://ks.example/soichi-hc")
    result = SearchResult(**{**result.__dict__, "title": "Soichi Hardcover Deluxe"})
    import_service.import_result(result)
    db_session.commit()
    assert db_session.scalar(select(StoreListing)).volume_id == cloth.id


def test_fallback_query_drops_variant_label(db_session):
    assert fallback_queries(db_session, "Soichi (Bez Cilt)")[0] == "Soichi"
    assert fallback_queries(db_session, "Soichi") == []


def test_sync_stores_publication_status(db_session):
    from dataclasses import replace

    manga = replace(_soichi(), jp_status="completed", tr_status="completed")
    CatalogSyncService(db_session, scraper=_Fake([manga])).sync()
    for title in ("Soichi", "Soichi (Bez Cilt)"):
        series = db_session.scalar(select(Series).where(Series.title == title))
        assert (series.jp_status, series.tr_status) == ("completed", "completed")


def test_variant_reclaims_its_isbn_from_the_base_series(db_session):
    """Production case: before the variant existed a store's clothbound
    "Soichi" (ISBN ...118) was title-matched and its ISBN stored on the
    regular volume. The Bez Cilt page proves whose ISBN it is: it moves to
    the variant and the regular volume reads its own ISBN again."""
    from app.scrapers.mangakol import CatalogVolumeDetails

    CatalogSyncService(db_session, scraper=FakeMangakolScraper([_soichi(with_variant=False)])).sync()
    regular = _volume(db_session, "Soichi")
    regular.isbn = CLOTH  # the wrong store ISBN, page never read
    db_session.commit()

    report = CatalogSyncService(db_session, scraper=_Fake([_soichi()])).sync()
    assert _volume(db_session, "Soichi (Bez Cilt)").isbn == CLOTH
    assert report.isbn_conflicts == 0
    regular = _volume(db_session, "Soichi")
    # The regular page was read before the variant in this sync (it kept
    # CLOTH then); cleared now, the next sync stores the regular ISBN.
    assert regular.isbn is None and regular.details_checked_at is None
    CatalogSyncService(db_session, scraper=_Fake([_soichi()])).sync()
    assert _volume(db_session, "Soichi").isbn == REGULAR


def test_isbn_of_an_unrelated_series_is_still_only_reported(db_session):
    from tests.test_import_service import seed_catalog_series

    other = seed_catalog_series(db_session, "Tomie", "Kayıp Kıta", volumes=(1,))
    held = db_session.scalar(select(Volume).where(Volume.series_id == other.id))
    held.isbn = CLOTH
    db_session.commit()
    report = CatalogSyncService(db_session, scraper=_Fake([_soichi()])).sync()
    assert held.isbn == CLOTH and _volume(db_session, "Soichi (Bez Cilt)").isbn is None
    assert report.isbn_conflicts == 1
