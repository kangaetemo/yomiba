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
from tests.test_alembic_upgrade import alembic_url  # noqa: F401 - fixture

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
    res = client.patch(f"/volume/{vol1}/collection-status", json={"status": "missing"})
    assert res.status_code == 200
    assert res.json()["collection_status"] == "missing"
    assert client.get(f"/volume/{vol1}").json()["collection_status"] == "missing"


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


def test_wanted_is_no_longer_a_collection_status(client, import_service, db_session):
    vol1, _, _ = _seed_berserk(import_service, db_session)
    assert client.patch(f"/volume/{vol1}/collection-status", json={"status": "wanted"}).status_code == 422


def test_series_page_reports_wishlisted_volumes(client, import_service, db_session):
    vol1, vol2, _ = _seed_berserk(import_service, db_session)
    client.post(f"/volume/{vol2}/wishlist")
    client.patch(f"/volume/{vol1}/collection-status", json={"status": "missing"})
    series_id = db_session.get(Volume, vol1).series_id
    by_id = {v["id"]: v for v in client.get(f"/series/{series_id}").json()["volumes"]}
    # "Bende yok" never puts a volume on the wishlist by itself.
    assert (by_id[vol1]["collection_status"], by_id[vol1]["wishlisted"]) == ("missing", False)
    assert (by_id[vol2]["collection_status"], by_id[vol2]["wishlisted"]) == (None, True)


def test_migration_moves_wanted_rows_to_the_wishlist(alembic_url):
    import sqlite3
    from alembic import command
    from alembic.config import Config
    from pathlib import Path

    db = alembic_url
    root = Path(__file__).resolve().parents[1]
    config = Config(str(root / "alembic.ini"))
    config.set_main_option("script_location", str(root / "alembic"))
    command.upgrade(config, "0019_price_alert_mail")

    def insert(c, table, **values):
        # Fill every NOT NULL column without a default; the test only cares
        # about the given values.
        for _, name, kind, notnull, default, pk in c.execute(f"PRAGMA table_info({table})"):
            if notnull and default is None and not pk and name not in values:
                values[name] = 0 if "INT" in kind.upper() or "BOOL" in kind.upper() else "2026-01-01"
        cols = ", ".join(values)
        c.execute(f"INSERT INTO {table} ({cols}) VALUES ({', '.join('?' * len(values))})", tuple(values.values()))

    with sqlite3.connect(db) as c:
        insert(c, "users", id=1, email="a@x", display_name="A", role="USER", is_active=1)
        insert(c, "publishers", id=1, name="P", normalized_name="p")
        insert(c, "series", id=1, publisher_id=1, title="S", slug="s", normalized_title="s")
        for vid in (1, 2, 3):
            insert(c, "volumes", id=vid, series_id=1, volume_number=vid)
        for vid, status in ((1, "owned"), (2, "wanted"), (3, "wanted")):
            insert(c, "user_volume_collections", user_id=1, volume_id=vid, status=status)
        insert(c, "wishlist_items", user_id=1, volume_id=3)
    command.upgrade(config, "0020_collection_two_states")
    with sqlite3.connect(db) as c:
        assert c.execute("SELECT volume_id, status FROM user_volume_collections").fetchall() == [(1, "owned")]
        assert sorted(r[0] for r in c.execute("SELECT volume_id FROM wishlist_items")) == [2, 3]
