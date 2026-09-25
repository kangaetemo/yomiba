"""Live Mangakol membership and legacy reconciliation regressions."""

from __future__ import annotations

import pytest
from sqlalchemy import select

from app.models import (
    CatalogExclusion, CatalogSeries, Publisher, PublisherAlias, Series, Volume,
)
from app.scrapers.mangakol import CatalogManga, CatalogVolume
from app.services import catalog_service
from app.services.catalog_reconciliation import reconcile_snapshot
from app.services.catalog_sync import CatalogSyncService
from app.services.import_service import ImportAction, ImportService
from app.scrapers import SearchResult
from tests.test_catalog_sync import FakeMangakolScraper, _manga


def _series(session, title, publisher, *, original=None, cover=None):
    pub = Publisher(name=publisher, normalized_name=publisher.lower())
    session.add(pub)
    session.flush()
    series = Series(
        publisher_id=pub.id, title=title,
        normalized_title=title.lower(), slug=title.lower().replace(" ", "-"),
        original_title=original,
    )
    session.add(series)
    session.flush()
    volume = Volume(series_id=series.id, volume_number=1, cover_url=cover)
    session.add(volume)
    session.flush()
    return series, volume


def test_legacy_exclusion_restores_same_series_and_catalog_behavior(db_session):
    series, volume = _series(db_session, "Kapital", "Yordam", cover="https://old-cover")
    db_session.add(CatalogExclusion(mangakol_slug="shin-shihonron"))
    db_session.commit()

    with db_session.begin():
        result = reconcile_snapshot(
            db_session, live_slugs={"shin-shihonron"},
            former_links={"shin-shihonron": series.id}, missing_manga={},
            slug_moves={},
        )
    assert result.restored_slugs == 1 and result.series_created == 0
    assert db_session.scalar(select(CatalogSeries.series_id)) == series.id
    assert db_session.get(CatalogExclusion, "shin-shihonron") is None
    assert db_session.get(Volume, volume.id).cover_url == "https://old-cover"
    assert catalog_service.get_series(db_session, series.id) is not None
    assert catalog_service.get_volume(db_session, volume.id) is not None
    assert catalog_service.search_series(db_session, "Kapital")

    result = SearchResult(
        store_id="bkm", store_name="BKM Kitap", title="Kapital 1",
        publisher="Yordam", product_url="https://example.test/kapital",
    )
    assert ImportService(db_session).import_result(result) == ImportAction.CREATED
    assert len(db_session.scalars(select(Series)).all()) == 1


def test_new_publisher_edition_stays_separate_from_restored_warcraft(db_session):
    old, old_volume = _series(db_session, "Warcraft Efsaneler", "Dogan Egmont")
    db_session.add(CatalogExclusion(mangakol_slug="warcraft-legends"))
    db_session.commit()
    new = CatalogManga(
        slug="warcraft-legends-epsilon", title="Warcraft Efsaneler (Epsilon)",
        local_publisher="Epsilon",
        volumes=[CatalogVolume(number=1, cover_url="https://new-cover")],
    )
    with db_session.begin():
        result = reconcile_snapshot(
            db_session,
            live_slugs={"warcraft-legends", "warcraft-legends-epsilon"},
            former_links={"warcraft-legends": old.id},
            missing_manga={new.slug: new}, slug_moves={},
        )
    assert result.series_created == 1
    rows = db_session.scalars(select(Series)).all()
    assert len(rows) == 2
    assert {r.publisher.name for r in rows} == {"Dogan Egmont", "Epsilon"}
    assert db_session.get(Volume, old_volume.id).series_id == old.id
    assert set(db_session.scalars(select(CatalogSeries.mangakol_slug))) == {
        "warcraft-legends", "warcraft-legends-epsilon",
    }


def test_verified_stale_slug_move_keeps_series_and_volume_ids(db_session):
    old, volume = _series(
        db_session, "JoJo's Bizarre Adventure", "Komikseyler Yayincilik",
        original="jojo no kimyou na bouken", cover="https://stale-cover",
    )
    db_session.add(PublisherAlias(
        normalized_alias="komik seyler", publisher_id=old.publisher_id,
    ))
    db_session.add(CatalogSeries(
        series_id=old.id, mangakol_slug="jojo-no-kimyou-na-bouken",
    ))
    db_session.commit()
    new = CatalogManga(
        slug="jojo-no-kimyou-na-bouken-part-1-phantom-blood",
        title="JoJo's Bizarre Adventure Part 1: Phantom Blood",
        local_publisher="Komik Seyler",
        original_title="JoJo no Kimyou na Bouken Part 1: Phantom Blood",
        volumes=[CatalogVolume(number=n, cover_url=f"https://new-cover/{n}")
                 for n in (1, 2, 3)],
    )
    with db_session.begin():
        result = reconcile_snapshot(
            db_session, live_slugs={new.slug}, former_links={},
            missing_manga={new.slug: new},
            slug_moves={"jojo-no-kimyou-na-bouken": new.slug},
        )
    assert result.moved_slugs == 1 and result.series_created == 0
    assert len(db_session.scalars(select(Series)).all()) == 1
    assert db_session.scalar(select(CatalogSeries.mangakol_slug)) == new.slug
    assert db_session.get(Series, old.id).title == new.title
    assert db_session.get(Volume, volume.id).cover_url == "https://new-cover/1"
    assert {v.volume_number for v in db_session.scalars(select(Volume))} == {1, 2, 3}


def test_stale_slug_move_rejects_title_only_identity(db_session):
    old, _ = _series(
        db_session, "JoJo's Bizarre Adventure", "First Publisher",
        original="jojo no kimyou na bouken",
    )
    db_session.add(CatalogSeries(series_id=old.id, mangakol_slug="old-jojo"))
    db_session.commit()
    new = CatalogManga(
        slug="new-jojo", title="JoJo's Bizarre Adventure Part 1",
        local_publisher="Different Publisher",
        original_title="JoJo no Kimyou na Bouken Part 1",
        volumes=[CatalogVolume(number=1, cover_url=None)],
    )
    with pytest.raises(ValueError, match="edition identity is unproven"):
        with db_session.begin():
            reconcile_snapshot(
                db_session, live_slugs={new.slug}, former_links={},
                missing_manga={new.slug: new},
                slug_moves={"old-jojo": new.slug},
            )
    assert db_session.scalar(select(CatalogSeries.mangakol_slug)) == "old-jojo"


def test_catalog_sync_represents_every_live_slug_even_with_legacy_exclusion(db_session):
    db_session.add(CatalogExclusion(mangakol_slug="legacy"))
    db_session.commit()
    mangas = [
        _manga("legacy", "Legacy", pub="Publisher One", volumes=(1,)),
        _manga("new", "New", pub="Publisher Two", volumes=(1,)),
    ]
    report = CatalogSyncService(
        db_session, scraper=FakeMangakolScraper(mangas)
    ).sync()
    assert report.ok and report.manga_skipped_excluded == 0
    assert set(db_session.scalars(select(CatalogSeries.mangakol_slug))) == {
        manga.slug for manga in mangas
    }


def test_ordinary_sync_reports_stale_slug_without_deleting_its_data(db_session):
    old, volume = _series(db_session, "Old Edition", "Publisher", cover="https://cover")
    db_session.add(CatalogSeries(series_id=old.id, mangakol_slug="old-slug"))
    db_session.commit()
    live = _manga("new-slug", "New Edition", pub="Other Publisher", volumes=(1,))
    report = CatalogSyncService(
        db_session, scraper=FakeMangakolScraper([live])
    ).sync()
    assert not report.ok
    assert any("stale manifest slugs" in error for error in report.errors)
    assert db_session.get(Series, old.id) is not None
    assert db_session.get(Volume, volume.id).cover_url == "https://cover"
