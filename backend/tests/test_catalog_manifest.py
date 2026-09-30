"""Catalog manifest: search serves only the series the Mangakol catalog
sync registered. Store-imported series (foreign editions, books, figures)
stay in the database — listings and price history intact — but out of the
search results, per the "search is the mangakol catalog" requirement.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import (
    CatalogSeries,
    Publisher,
    Series,
    Store,
    StoreListing,
    Volume,
)
from app.services import catalog_service
from app.services.catalog_sync import CatalogSyncService
from tests.test_catalog_sync import FakeMangakolScraper, _manga


# -- the sync registers catalog series -------------------------------------------

def test_sync_marks_created_series(db_session):
    manga = _manga("frieren", "Frieren", pub="Marmara Çizgi", volumes=(1,))
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    assert report.series_created == 1

    rows = db_session.scalars(select(CatalogSeries)).all()
    assert len(rows) == 1
    series = db_session.scalars(select(Series)).one()
    assert rows[0].series_id == series.id
    assert rows[0].mangakol_slug == "frieren"


def test_sync_merge_registers_existing_series(db_session):
    """A series that only a store import knew (under Bilinmiyor) becomes
    catalog once the sync merges a mangakol entry into it."""
    bilinmiyor = Publisher(name="Bilinmiyor", normalized_name="bilinmiyor")
    db_session.add(bilinmiyor)
    db_session.flush()
    series = Series(
        publisher_id=bilinmiyor.id, title="Frieren",
        normalized_title="frieren", slug="frieren",
    )
    db_session.add(series)
    db_session.flush()
    db_session.add(Volume(series_id=series.id, volume_number=1))
    db_session.commit()
    assert db_session.scalar(
        select(CatalogSeries.series_id).where(CatalogSeries.series_id == series.id)
    ) is None

    manga = _manga("frieren", "Frieren", pub="Marmara Çizgi", volumes=(1, 2))
    report = CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()
    assert report.series_merged == 1
    assert db_session.scalar(
        select(CatalogSeries.series_id).where(CatalogSeries.series_id == series.id)
    ) == series.id


def test_sync_manifest_is_idempotent(db_session):
    manga = _manga("frieren", "Frieren", pub="Marmara Çizgi", volumes=(1,))
    scraper = FakeMangakolScraper([manga])
    CatalogSyncService(db_session, scraper=scraper).sync()
    CatalogSyncService(db_session, scraper=scraper).sync()
    assert (
        db_session.scalar(select(func.count(CatalogSeries.series_id))) == 1
    )


# -- search is catalog-only --------------------------------------------------------

def test_search_returns_only_catalog_series(db_session):
    # catalog series (created by the sync)
    manga = _manga("frieren", "Frieren", pub="Marmara Çizgi", volumes=(1,))
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    # non-catalog series sharing the "frieren" stem (a foreign edition)
    pub = Publisher(name="Viz Media", normalized_name="viz media")
    db_session.add(pub)
    db_session.flush()
    other = Series(
        publisher_id=pub.id, title="Frieren: Beyond Journey's End",
        normalized_title="frieren beyond journey's end",
        slug="frieren-viz",
    )
    db_session.add(other)
    db_session.flush()
    db_session.add(Volume(series_id=other.id, volume_number=1))
    db_session.commit()

    titles = {m.series.title for m in catalog_service.search_series(db_session, "frieren")}
    assert titles == {"Frieren"}  # only the catalog series


def test_search_excludes_non_catalog_even_with_listings(db_session):
    """Store-imported data (with live listings) is still kept out of search
    unless the catalog sync has registered the series."""
    store = Store(code="bkm", name="BKM Kitap")
    db_session.add(store)
    db_session.flush()
    pub = Publisher(name="Banpresto", normalized_name="banpresto")
    db_session.add(pub)
    db_session.flush()
    series = Series(
        publisher_id=pub.id, title="Frieren Figure",
        normalized_title="frieren figure", slug="frieren-figure",
    )
    db_session.add(series)
    db_session.flush()
    volume = Volume(series_id=series.id, volume_number=-1)
    db_session.add(volume)
    db_session.flush()
    db_session.add(
        StoreListing(volume_id=volume.id, store_id=store.id,
                     product_url="https://bkm.example/f", price=39900)
    )
    db_session.commit()

    assert catalog_service.search_series(db_session, "frieren") == []
    # Direct detail lookup must respect the same catalog boundary.
    detail = catalog_service.get_series(db_session, series.id)
    assert detail is None
    assert catalog_service.get_volume(db_session, volume.id) is None
    # Existing data stays intact until a safe cleanup is approved.
    assert db_session.scalar(select(StoreListing)) is not None


def test_search_empty_catalog_returns_nothing(db_session):
    """A fresh DB with only store data (no sync yet) has no search results."""
    pub = Publisher(name="Dark Horse Manga", normalized_name="dark horse manga")
    db_session.add(pub)
    db_session.flush()
    series = Series(
        publisher_id=pub.id, title="Berserk",
        normalized_title="berserk", slug="berserk",
    )
    db_session.add(series)
    db_session.flush()
    db_session.add(Volume(series_id=series.id, volume_number=1))
    db_session.commit()

    assert catalog_service.search_series(db_session, "berserk") == []


# -- search by original (foreign) title ---------------------------------------------

def test_search_matches_original_title(db_session):
    """'Tokyo Ghoul' finds the Turkish-edition series 'Tokyo Gül' via the
    original-title key stored by the catalog sync."""
    manga = _manga(
        "tokyo-ghoul", "Tokyo Gül", pub="Gerekli Şeyler Yayıncılık",
        volumes=(1,), original="Tokyo Ghoul | 東京喰種トーキョーグール",
    )
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    for query in ("tokyo ghoul", "Tokyo Ghoul", "ghoul", "tokyo gul"):
        titles = {m.series.title for m in catalog_service.search_series(db_session, query)}
        assert titles == {"Tokyo Gül"}, query


def test_search_original_title_still_catalog_only(db_session):
    """The original-title match path respects the manifest filter too: a
    non-catalog series with the same original title stays out of search."""
    manga = _manga(
        "tokyo-ghoul", "Tokyo Gül", pub="Gerekli Şeyler Yayıncılık",
        volumes=(1,), original="Tokyo Ghoul",
    )
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([manga])).sync()

    pub = Publisher(name="Viz Media", normalized_name="viz media")
    db_session.add(pub)
    db_session.flush()
    foreign = Series(
        publisher_id=pub.id, title="Tokyo Ghoul",
        normalized_title="tokyo ghoul", slug="tokyo-ghoul-viz",
        original_title="tokyo ghoul",
    )
    db_session.add(foreign)
    db_session.flush()
    db_session.add(Volume(series_id=foreign.id, volume_number=1))
    db_session.commit()

    titles = {m.series.title for m in catalog_service.search_series(db_session, "ghoul")}
    assert titles == {"Tokyo Gül"}  # the Viz edition is not in the catalog


def test_search_ranks_word_start_matches_first(db_session):
    """Typing "one" shows One Piece (and One Punch Man) before series that
    merely contain the letters ("Dr. Stone", "Monotone Blue")."""
    mangas = [
        _manga("dr-stone", "Dr. Stone", pub="Gerekli Şeyler Yayıncılık", volumes=(1,)),
        _manga("monotone-blue", "Monotone Blue", pub="Athica", volumes=(1,)),
        _manga("joker", "Joker: Tek Kişilik Operasyon", pub="JBC", volumes=(1,),
               original="One Operation Joker"),
        _manga("one-punch-man", "One Punch Man", pub="Gerekli Şeyler Yayıncılık", volumes=(1,)),
        _manga("one-piece", "One Piece", pub="Gerekli Şeyler Yayıncılık", volumes=(1,)),
    ]
    CatalogSyncService(db_session, scraper=FakeMangakolScraper(mangas)).sync()

    titles = [m.series.title for m in catalog_service.search_series(db_session, "one")]
    assert titles[:2] == ["One Piece", "One Punch Man"]
    assert set(titles[2:]) == {"Dr. Stone", "Monotone Blue", "Joker: Tek Kişilik Operasyon"}
    assert [m.series.title for m in catalog_service.search_series(db_session, "piece")][0] == "One Piece"
