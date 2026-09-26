"""Wishlist + price alerts (Phase 25).

Covers the spec scenarios:
  * wishlist: add, idempotent re-add, remove, idempotent re-remove, 404,
    correct state reporting
  * price alerts: create, view, threshold change, delete, activate/pause,
    single-row per volume, 0 / negative / invalid rejected, 404
  * independence: collection_status + wishlist + alert all survive a
    re-import (ImportService must not touch any of them)

No notification infrastructure exists; these tests only verify the stored
state and the API surface.
"""

from __future__ import annotations

from sqlalchemy import func, select

from app.models import PriceAlert, Volume, WishlistItem
from tests.test_import_service import do_import, make_result, seed_catalog_series

ISBN = "9786051234567"


def _seed(import_service, db_session) -> tuple[int, int]:
    seed_catalog_series(db_session, "Berserk", "Athica Yayınları", volumes=(1, 2))
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "169", isbn=ISBN, publisher="Athica Yayınları"),
        make_result("bkm", "Berserk 2", "182", publisher="Athica Yayınları"),
    )
    vol1 = db_session.scalar(select(Volume).where(Volume.volume_number == 1))
    vol2 = db_session.scalar(select(Volume).where(Volume.volume_number == 2))
    return vol1.id, vol2.id


# ---------------------------------------------------------------------------
# Wishlist
# ---------------------------------------------------------------------------
def test_wishlist_add_and_state(client, import_service, db_session):
    vol1, _ = _seed(import_service, db_session)

    res = client.post(f"/volume/{vol1}/wishlist")
    assert res.status_code == 200
    assert res.json() == {"volume_id": vol1, "wishlisted": True}

    assert client.get(f"/volume/{vol1}/wishlist").json() == {
        "volume_id": vol1,
        "wishlisted": True,
    }
    assert (
        db_session.scalar(select(func.count()).select_from(WishlistItem)) == 1
    )


def test_wishlist_readd_is_idempotent_no_duplicate(client, import_service, db_session):
    vol1, _ = _seed(import_service, db_session)

    assert client.post(f"/volume/{vol1}/wishlist").status_code == 200
    res = client.post(f"/volume/{vol1}/wishlist")  # second add
    assert res.status_code == 200
    assert res.json()["wishlisted"] is True
    assert (
        db_session.scalar(select(func.count()).select_from(WishlistItem)) == 1
    )  # still exactly one row


def test_wishlist_remove_and_reremove_idempotent(client, import_service, db_session):
    vol1, _ = _seed(import_service, db_session)
    client.post(f"/volume/{vol1}/wishlist")

    res = client.delete(f"/volume/{vol1}/wishlist")
    assert res.status_code == 200
    assert res.json() == {"volume_id": vol1, "wishlisted": False}
    assert db_session.scalar(select(func.count()).select_from(WishlistItem)) == 0

    # Removing an already-removed volume is safe.
    res = client.delete(f"/volume/{vol1}/wishlist")
    assert res.status_code == 200
    assert res.json()["wishlisted"] is False


def test_wishlist_unknown_volume_404(client, import_service, db_session):
    _seed(import_service, db_session)
    assert client.get("/volume/9999/wishlist").status_code == 404
    assert client.post("/volume/9999/wishlist").status_code == 404
    assert client.delete("/volume/9999/wishlist").status_code == 404


def test_wishlist_get_on_fresh_volume_is_false(client, import_service, db_session):
    vol2, _ = _seed(import_service, db_session)
    assert client.get(f"/volume/{vol2}/wishlist").json()["wishlisted"] is False


# ---------------------------------------------------------------------------
# Price alerts
# ---------------------------------------------------------------------------
def test_price_alert_create_and_view(client, import_service, db_session):
    vol1, _ = _seed(import_service, db_session)

    res = client.put(f"/volume/{vol1}/price-alert", json={"threshold_price": 15000})
    assert res.status_code == 200
    body = res.json()
    assert body["volume_id"] == vol1
    assert body["alert"]["threshold_price"] == 15000
    assert body["alert"]["is_active"] is True
    assert body["alert"]["id"]

    got = client.get(f"/volume/{vol1}/price-alert").json()
    assert got["alert"]["threshold_price"] == 15000
    assert got["alert"]["is_active"] is True


def test_price_alert_threshold_update_keeps_single_row(client, import_service, db_session):
    vol1, _ = _seed(import_service, db_session)

    first = client.put(f"/volume/{vol1}/price-alert", json={"threshold_price": 15000}).json()
    second = client.put(f"/volume/{vol1}/price-alert", json={"threshold_price": 12000}).json()

    assert second["alert"]["threshold_price"] == 12000
    assert second["alert"]["id"] == first["alert"]["id"]  # updated, not created
    assert (
        db_session.scalar(select(func.count()).select_from(PriceAlert)) == 1
    )


def test_price_alert_pause_and_activate(client, import_service, db_session):
    vol1, _ = _seed(import_service, db_session)
    client.put(f"/volume/{vol1}/price-alert", json={"threshold_price": 15000})

    paused = client.put(f"/volume/{vol1}/price-alert", json={"is_active": False}).json()
    assert paused["alert"]["is_active"] is False
    assert paused["alert"]["threshold_price"] == 15000  # untouched

    active = client.put(f"/volume/{vol1}/price-alert", json={"is_active": True}).json()
    assert active["alert"]["is_active"] is True
    assert active["alert"]["threshold_price"] == 15000
    assert (
        db_session.scalar(select(func.count()).select_from(PriceAlert)) == 1
    )


def test_price_alert_threshold_update_reactivates_paused(client, import_service, db_session):
    vol1, _ = _seed(import_service, db_session)
    client.put(f"/volume/{vol1}/price-alert", json={"threshold_price": 15000})
    client.put(f"/volume/{vol1}/price-alert", json={"is_active": False})

    updated = client.put(f"/volume/{vol1}/price-alert", json={"threshold_price": 12000}).json()
    assert updated["alert"]["threshold_price"] == 12000
    assert updated["alert"]["is_active"] is True  # re-setting a price re-activates
    assert (
        db_session.scalar(select(func.count()).select_from(PriceAlert)) == 1
    )


def test_price_alert_delete_idempotent(client, import_service, db_session):
    vol1, _ = _seed(import_service, db_session)
    client.put(f"/volume/{vol1}/price-alert", json={"threshold_price": 15000})

    res = client.delete(f"/volume/{vol1}/price-alert")
    assert res.status_code == 200
    assert res.json() == {"volume_id": vol1, "alert": None}
    assert db_session.scalar(select(func.count()).select_from(PriceAlert)) == 0

    # Deleting again is safe.
    res = client.delete(f"/volume/{vol1}/price-alert")
    assert res.status_code == 200
    assert res.json()["alert"] is None
    assert client.get(f"/volume/{vol1}/price-alert").json()["alert"] is None


def test_price_alert_invalid_thresholds_rejected(client, import_service, db_session):
    vol1, _ = _seed(import_service, db_session)
    for bad in (0, -5, "abc", 150.5):
        res = client.put(f"/volume/{vol1}/price-alert", json={"threshold_price": bad})
        assert res.status_code == 422, f"threshold {bad!r} must be rejected"
    # Nothing was created by the rejected puts.
    assert client.get(f"/volume/{vol1}/price-alert").json()["alert"] is None


def test_price_alert_create_requires_threshold(client, import_service, db_session):
    vol1, _ = _seed(import_service, db_session)
    # No alert exists yet: a body without a threshold is invalid.
    assert client.put(f"/volume/{vol1}/price-alert", json={}).status_code == 422
    # ...but once an alert exists, a state-only update is fine.
    client.put(f"/volume/{vol1}/price-alert", json={"threshold_price": 15000})
    assert (
        client.put(f"/volume/{vol1}/price-alert", json={"is_active": False}).status_code
        == 200
    )


def test_price_alert_unknown_volume_404(client, import_service, db_session):
    _seed(import_service, db_session)
    assert client.get("/volume/9999/price-alert").status_code == 404
    assert client.put("/volume/9999/price-alert", json={"threshold_price": 100}).status_code == 404
    assert client.delete("/volume/9999/price-alert").status_code == 404


# ---------------------------------------------------------------------------
# Independence from imports
# ---------------------------------------------------------------------------
def test_import_does_not_touch_collection_wishlist_or_alert(
    client, import_service, db_session
):
    """Spec scenario: owned + wishlisted + alerted volume survives re-import."""
    vol1, _ = _seed(import_service, db_session)

    # 1. collection_status = owned
    assert (
        client.patch(f"/volume/{vol1}/collection-status", json={"status": "owned"})
        .json()["collection_status"]
        == "owned"
    )
    # 2. wishlist
    assert client.post(f"/volume/{vol1}/wishlist").json()["wishlisted"] is True
    # 3. price alert
    assert client.put(f"/volume/{vol1}/price-alert", json={"threshold_price": 15000}).status_code == 200

    # 4. re-import the same volume (new price, same ISBN).
    do_import(
        import_service,
        db_session,
        make_result("bkm", "Berserk 1", "155", isbn=ISBN, publisher="Athica Yayınları"),
    )

    # 5. all three are still there — and the import itself still worked.
    detail = client.get(f"/volume/{vol1}").json()
    assert detail["collection_status"] == "owned"
    assert client.get(f"/volume/{vol1}/wishlist").json()["wishlisted"] is True
    alert = client.get(f"/volume/{vol1}/price-alert").json()["alert"]
    assert alert is not None
    assert alert["threshold_price"] == 15000
    assert alert["is_active"] is True
    assert [s["price"] for s in detail["stores"]] == [155.0]  # import applied

    # Row-level: exactly one of each, none deleted/recreated by the import.
    assert db_session.scalar(select(func.count()).select_from(WishlistItem)) == 1
    assert db_session.scalar(select(func.count()).select_from(PriceAlert)) == 1
