"""Collections: volume status (owned / missing / wanted) set, change, clear.

Regression coverage for the Phase 24 foundation:
  * status is exposed on GET /volume/{id} and GET /series/{id}
  * PATCH accepts the three statuses and ``null`` (clear)
  * invalid status -> 422, unknown volume -> 404
  * re-importing a tracked volume never wipes its status
"""

from __future__ import annotations

from sqlalchemy import select

from app.models import Volume
from tests.test_import_service import do_import, make_result, seed_catalog_series

ISBN = "9786051234567"


def _seed_berserk(import_service, db_session) -> tuple[int, int, int]:
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1, 2))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn=ISBN, publisher="Athica Yayınları"),
        make_result("bkm", "Berserk 2", "182", publisher="Athica Yayınları"),
    )
    vol1 = db_session.scalar(select(Volume).where(Volume.volume_number == 1))
    vol2 = db_session.scalar(select(Volume).where(Volume.volume_number == 2))
    return vol1.id, vol2.id, vol1.series_id


def test_new_volume_defaults_to_untracked(client, import_service, db_session):
    vol1, _, _ = _seed_berserk(import_service, db_session)
    assert client.get(f"/volume/{vol1}").json()["collection_status"] is None


def test_set_owned_persists_and_appears_on_volume_and_series(
    client, import_service, db_session
):
    vol1, vol2, series_id = _seed_berserk(import_service, db_session)

    res = client.patch(f"/volume/{vol1}/collection-status", json={"status": "owned"})
    assert res.status_code == 200
    assert res.json()["collection_status"] == "owned"

    assert client.get(f"/volume/{vol1}").json()["collection_status"] == "owned"
    series = client.get(f"/series/{series_id}").json()
    by_id = {v["id"]: v for v in series["volumes"]}
    assert by_id[vol1]["collection_status"] == "owned"
    assert by_id[vol2]["collection_status"] is None  # untouched


def test_change_status(client, import_service, db_session):
    vol1, _, _ = _seed_berserk(import_service, db_session)
    client.patch(f"/volume/{vol1}/collection-status", json={"status": "owned"})
    res = client.patch(f"/volume/{vol1}/collection-status", json={"status": "wanted"})
    assert res.status_code == 200
    assert res.json()["collection_status"] == "wanted"
    assert client.get(f"/volume/{vol1}").json()["collection_status"] == "wanted"


def test_clear_status_with_null(client, import_service, db_session):
    vol1, _, _ = _seed_berserk(import_service, db_session)
    client.patch(f"/volume/{vol1}/collection-status", json={"status": "missing"})
    res = client.patch(f"/volume/{vol1}/collection-status", json={"status": None})
    assert res.status_code == 200
    assert res.json()["collection_status"] is None


def test_invalid_status_rejected(client, import_service, db_session):
    vol1, _, _ = _seed_berserk(import_service, db_session)
    res = client.patch(f"/volume/{vol1}/collection-status", json={"status": "burnt"})
    assert res.status_code == 422
    # The volume itself is unaffected.
    assert client.get(f"/volume/{vol1}").json()["collection_status"] is None


def test_missing_status_field_rejected(client, import_service, db_session):
    vol1, _, _ = _seed_berserk(import_service, db_session)
    assert client.patch(f"/volume/{vol1}/collection-status", json={}).status_code == 422


def test_unknown_volume_404(client, import_service, db_session):
    res = client.patch("/volume/9999/collection-status", json={"status": "owned"})
    assert res.status_code == 404


def test_reimport_does_not_wipe_status(client, import_service, db_session):
    vol1, _, _ = _seed_berserk(import_service, db_session)
    client.patch(f"/volume/{vol1}/collection-status", json={"status": "owned"})

    # A full re-import of the same volume (new price, same ISBN).
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "165", isbn=ISBN, publisher="Athica Yayınları"),
    )
    assert client.get(f"/volume/{vol1}").json()["collection_status"] == "owned"
    # And the re-import itself still worked (price updated).
    prices = [s["price"] for s in client.get(f"/volume/{vol1}").json()["stores"]]
    assert prices == [165.0]
