"""Keep source placeholders out of public shelves without deleting data."""
from sqlalchemy import select
from app.models import CatalogSeries, User, UserVolumeCollection, Volume
from app.scrapers.mangakol import CatalogManga, CatalogVolume
from app.services.catalog_sync import CatalogSyncService
from tests.test_catalog_sync import FakeMangakolScraper
from tests.test_import_service import seed_catalog_series


def _snapshot(numbers=(1, 2), announced=(3,), complete=True):
    return CatalogManga(slug="fairy-tail", title="Fairy Tail", local_publisher="Gerekli Şeyler",
                        volumes=[CatalogVolume(number=n, cover_url=None, released=n not in announced) for n in numbers],
                        volumes_complete=complete)


def _seed(session):
    series = seed_catalog_series(session, "Fairy Tail", "Gerekli Şeyler", volumes=(1, 2, 3, 63))
    # Test helper's slug uses the same normalized work identity.
    manifest = session.scalar(select(CatalogSeries).where(CatalogSeries.series_id == series.id))
    manifest.mangakol_slug = "fairy-tail"
    session.commit()
    return series


def test_complete_snapshot_hides_extra_and_announced_without_deleting_user_data(db_session, client):
    series = _seed(db_session)
    extra = db_session.scalar(select(Volume).where(Volume.series_id == series.id, Volume.volume_number == 63))
    user = db_session.scalar(select(User))
    db_session.add(UserVolumeCollection(user_id=user.id, volume_id=extra.id, status="owned"))
    db_session.commit()
    snapshot = _snapshot((1, 2, 3))
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([snapshot])).sync()
    assert [v["number"] for v in client.get(f"/series/{series.id}").json()["volumes"]] == [1, 2]
    assert client.get("/search?q=fairy").json()["results"][0]["volume_count"] == 2
    assert db_session.get(Volume, extra.id) is not None
    assert db_session.scalar(select(UserVolumeCollection).where(UserVolumeCollection.volume_id == extra.id)) is not None
    assert client.get(f"/volume/{extra.id}").status_code == 404


def test_partial_snapshot_does_not_hide_unseen_volumes(db_session, client):
    series = _seed(db_session)
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([_snapshot((1, 2), complete=False)])).sync()
    assert [v["number"] for v in client.get(f"/series/{series.id}").json()["volumes"]] == [1, 2, 3, 63]


def test_unknown_metadata_does_not_remove_a_released_volume(db_session, client):
    series = _seed(db_session)
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([_snapshot((1, 2, 3), announced=())])).sync()
    assert [v["number"] for v in client.get(f"/series/{series.id}").json()["volumes"]] == [1, 2, 3]


def test_announced_volume_appears_when_source_marks_it_released(db_session, client):
    series = _seed(db_session)
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([_snapshot((1, 2, 3))])).sync()
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([_snapshot((1, 2, 3), announced=())])).sync()
    assert [v["number"] for v in client.get(f"/series/{series.id}").json()["volumes"]] == [1, 2, 3]


def test_empty_snapshot_never_retires_all_volumes(db_session, client):
    series = _seed(db_session)
    CatalogSyncService(db_session, scraper=FakeMangakolScraper([_snapshot(())])).sync()
    assert len(client.get(f"/series/{series.id}").json()["volumes"]) == 4
