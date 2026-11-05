"""Pre-orders: a store may sell a volume the catalog still lists as
"Yakında" (Komik Şeyler's JoJo Limitli Baskı before release)."""
from sqlalchemy import select

from app.models import StoreListing, Volume
from app.services.import_service import ImportAction, ImportService
from tests.test_import_service import make_result, seed_catalog_series


def _announced_series(session):
    series = seed_catalog_series(session, "Fairy Tail", "Gerekli Şeyler", volumes=(1, 2, 3))
    for volume in session.scalars(select(Volume).where(Volume.series_id == series.id)):
        volume.catalog_present = True
        volume.catalog_released = volume.volume_number == 1
    session.commit()
    return series


def _volume(session, series, number):
    return session.scalar(select(Volume).where(
        Volume.series_id == series.id, Volume.volume_number == number))


def test_preorder_listing_attaches_to_announced_volume(db_session, client):
    series = _announced_series(db_session)
    service = ImportService(db_session)
    result = make_result("bkm", "Fairy Tail 2", "450", publisher="Gerekli Şeyler")
    assert service.import_result(result) == ImportAction.CREATED
    db_session.commit()
    volume = _volume(db_session, series, 2)
    assert db_session.scalar(select(StoreListing.volume_id)) == volume.id

    body = client.get(f"/series/{series.id}").json()
    by_number = {v["number"]: v for v in body["volumes"]}
    assert sorted(by_number) == [1, 2]
    assert by_number[2]["preorder"] is True and by_number[2]["best_price"] == 450
    assert by_number[1]["preorder"] is False
    assert [v["number"] for v in body["upcoming_volumes"]] == [3]

    page = client.get(f"/volume/{volume.id}")
    assert page.status_code == 200 and page.json()["preorder"] is True
    assert client.get(f"/volume/{_volume(db_session, series, 3).id}").status_code == 404


def test_retired_volume_still_takes_no_listing(db_session):
    series = _announced_series(db_session)
    _volume(db_session, series, 2).catalog_present = False
    db_session.commit()
    service = ImportService(db_session)
    result = make_result("bkm", "Fairy Tail 2", "450", publisher="Gerekli Şeyler")
    assert service.import_result(result) == ImportAction.SKIPPED
    assert service.last_reason == "non_catalog_volume"
