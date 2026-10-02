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


SOLO = "https://mangakol.com/manga/solo-leveling"
SHARED = "9786255607782"


class _SoloFake(FakeMangakolScraper):
    def fetch_volume_details(self, url):
        from app.scrapers.mangakol import CatalogVolumeDetails

        return CatalogVolumeDetails(isbn=SHARED if url.endswith(("-variant", "-limited")) else None)


def _solo() -> CatalogManga:
    return CatalogManga(
        slug="solo-leveling", title="Solo Leveling", local_publisher="Komikşeyler",
        volumes=[CatalogVolume(number=5, cover_url=None, url=f"{SOLO}/cilt-5")],
        variants=(
            CatalogVariant("Limited", "Limitli Baskı", [CatalogVolume(number=5, cover_url=None, url=f"{SOLO}/cilt-5-limited")]),
            CatalogVariant("Variant", "Varyant Kapak", [CatalogVolume(number=5, cover_url=None, url=f"{SOLO}/cilt-5-variant")]),
        ),
    )


def test_two_editions_sharing_one_isbn_are_told_apart_by_title(db_session):
    """Komikşeyler printed Solo Leveling 5 "Varyant Kapak" and "Limitli
    Baskı" under one ISBN: only one volume can hold it, so the edition the
    product title names decides — and a listing the ISBN once put on the
    other edition moves with it."""
    CatalogSyncService(db_session, scraper=_SoloFake([_solo()])).sync()
    limited, variant = _volume(db_session, "Solo Leveling (Limitli Baskı)"), _volume(db_session, "Solo Leveling (Varyant Kapak)")
    assert (limited.isbn, variant.isbn) == (None, SHARED)  # the listed owner keeps it

    store = Store(code="bkm", name="BKM Kitap")
    db_session.add(store)
    db_session.flush()
    db_session.add(StoreListing(volume_id=limited.id, store_id=store.id,
                                product_url="https://ks.example/sl5-varyant", price=30000))
    db_session.commit()

    def product(title, price, url):
        return SearchResult(
            store_id="bkm", store_name="BKM Kitap", title=title, product_url=url,
            isbn=SHARED, publisher="Komikşeyler", price=Decimal(price), currency="TRY", in_stock=True,
        )

    scrapers = _fake_scrapers({"bkm": [
        product("Solo Leveling 5 (Varyant Kapak)", "300", "https://ks.example/sl5-varyant"),
        product("Solo Leveling 5 (Limitli Baskı)", "450", "https://ks.example/sl5-limitli"),
    ]}, failing=set())
    ImportService(db_session, scrapers=scrapers).run_import("Solo Leveling")

    listings = {l.volume_id: (l.product_url, l.price) for l in db_session.scalars(select(StoreListing))}
    assert listings == {
        variant.id: ("https://ks.example/sl5-varyant", 30000),
        limited.id: ("https://ks.example/sl5-limitli", 45000),
    }


def _solo_product(title, price, url, isbn=None):
    return SearchResult(
        store_id="bkm", store_name="BKM Kitap", title=title, product_url=url,
        isbn=isbn, publisher="Komikşeyler", price=Decimal(price), currency="TRY", in_stock=True,
    )


def test_shared_isbn_moves_to_its_listed_owner(db_session):
    """The variant cover is the edition stores sell under the shared ISBN:
    the sync hands it over and no longer reports a conflict."""
    CatalogSyncService(db_session, scraper=_SoloFake([_solo()])).sync()
    report = CatalogSyncService(db_session, scraper=_SoloFake([_solo()])).sync()
    limited, variant = _volume(db_session, "Solo Leveling (Limitli Baskı)"), _volume(db_session, "Solo Leveling (Varyant Kapak)")
    assert (limited.isbn, variant.isbn) == (None, SHARED)
    assert report.isbn_conflicts == 0


def test_editions_without_isbn_are_matched_by_their_title_words(db_session):
    """No ISBN to go by: the label words place the product ("Limitli Sert
    Kapak" is the catalog's "Limitli Baskı"); a plain title is not guessed."""
    CatalogSyncService(db_session, scraper=_SoloFake([_solo()])).sync()
    limited, variant = _volume(db_session, "Solo Leveling (Limitli Baskı)"), _volume(db_session, "Solo Leveling (Varyant Kapak)")
    for volume in (limited, variant):
        volume.isbn = None
    db_session.commit()

    scrapers = _fake_scrapers({"bkm": [
        _solo_product("Solo Leveling Webtoon Cilt 5 (Limitli Sert Kapak)", "1400", "https://ks.example/sl5-sert"),
        _solo_product("Solo Leveling Manga Cilt 5 (Kuşe Kağıt - Varyant Kapak)", "553", "https://ks.example/sl5-kuse"),
    ]}, failing=set())
    ImportService(db_session, scrapers=scrapers).run_import("Solo Leveling")

    listings = {l.volume_id: l.price for l in db_session.scalars(select(StoreListing))}
    assert listings == {limited.id: 140000, variant.id: 55300}


def test_ana_kapak_title_with_a_variant_isbn_goes_to_the_main_edition(db_session):
    """A store put the limited edition's ISBN on the regular book: its
    531 TL must not show as the price of the 1400 TL hardcover."""
    CatalogSyncService(db_session, scraper=_SoloFake([_solo()])).sync()
    regular, limited = _volume(db_session, "Solo Leveling"), _volume(db_session, "Solo Leveling (Limitli Baskı)")
    limited.isbn = "9786052115640"
    db_session.commit()

    scrapers = _fake_scrapers({"bkm": [
        _solo_product("Solo Leveling Webtoon Cilt 5 (2. Hamur – Ana Kapak)", "531.25", "https://ks.example/sl5-ana", isbn=limited.isbn),
    ]}, failing=set())
    ImportService(db_session, scrapers=scrapers).run_import("Solo Leveling")

    assert [l.volume_id for l in db_session.scalars(select(StoreListing))] == [regular.id]
