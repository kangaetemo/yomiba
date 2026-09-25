"""Account isolation, authorization, session and CSRF regressions."""

from datetime import timedelta

from sqlalchemy import select

from app.auth import COOKIE_NAME, token_digest
from app.models import User, UserSession, UserVolumeCollection, WishlistItem, PriceAlert
from app.utils import utcnow
from tests.test_import_service import seed_catalog_series
from app.services.catalog_sync import CatalogSyncService
from app.models import Volume
import pytest


def _register(client, email: str):
    client.cookies.clear()
    response = client.post("/auth/register", json={
        "email": email, "password": "correct horse battery staple",
        "display_name": email.split("@")[0],
    })
    assert response.status_code == 201, response.text
    return response, client.cookies.get(COOKIE_NAME)


def test_register_login_logout_and_secret_handling(client, db_session):
    response, token = _register(client, "ALICE@Example.COM")
    assert response.json()["email"] == "alice@example.com"
    assert "password_hash" not in response.json()
    assert token not in response.text
    assert "httponly" in response.headers["set-cookie"].lower()
    assert "secure" in response.headers["set-cookie"].lower()
    user = db_session.scalar(select(User).where(User.email == "alice@example.com"))
    assert user.password_hash.startswith("$argon2id$")
    assert "correct horse" not in user.password_hash
    assert db_session.scalar(select(UserSession.token_hash).where(UserSession.user_id == user.id)) == token_digest(token)
    assert client.get("/auth/me").json()["id"] == user.id
    assert client.post("/auth/register", json={"email": "alice@example.com", "password": "correct horse battery staple", "display_name": "Duplicate"}).status_code == 409
    client.cookies.clear()
    assert client.get("/auth/me").status_code == 401
    bad = client.post("/auth/login", json={"email": "alice@example.com", "password": "wrong"})
    assert bad.status_code == 401
    assert client.post("/auth/login", json={"email": "missing@example.com", "password": "wrong"}).json() == bad.json()
    assert client.post("/auth/login", json={"email": "ALICE@example.com", "password": "correct horse battery staple"}).status_code == 200
    login_token = client.cookies.get(COOKIE_NAME)
    assert client.post("/auth/logout").status_code == 204
    client.cookies.set(COOKIE_NAME, login_token)
    assert client.get("/auth/me").status_code == 401
    client.cookies.set(COOKIE_NAME, token)
    assert client.get("/auth/me").status_code == 200


def test_expiry_invalid_cookie_and_csrf(client, db_session):
    _, token = _register(client, "session@example.com")
    row = db_session.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))
    row.expires_at = utcnow() - timedelta(seconds=1)
    db_session.commit()
    assert client.get("/auth/me").status_code == 401
    client.cookies.set(COOKIE_NAME, "forged-token")
    assert client.get("/auth/me").status_code == 401
    client.cookies.clear()
    assert client.post("/auth/register", headers={"Origin": "https://evil.example"}, json={"email": "x@example.com", "password": "correct horse battery staple", "display_name": "X"}).status_code == 403
    assert client.post("/auth/register", headers={"Origin": ""}, json={"email": "x@example.com", "password": "correct horse battery staple", "display_name": "X"}).status_code == 403


def test_public_reads_and_admin_authorization(client, db_session):
    admin_token = client.cookies.get(COOKIE_NAME)
    assert client.get("/import/records").status_code == 200
    series = seed_catalog_series(db_session, "Auth Manga", "Auth Publisher", volumes=(1,))
    volume = series.volumes[0]
    client.cookies.clear()
    assert client.get("/search?q=Auth").status_code == 200
    assert client.get(f"/series/{series.id}").status_code == 200
    assert client.get(f"/volume/{volume.id}").json()["collection_status"] is None
    assert client.patch(f"/volume/{volume.id}/collection-status", json={"status": "owned"}).status_code == 401
    assert client.post(f"/volume/{volume.id}/wishlist").status_code == 401
    assert client.put(f"/volume/{volume.id}/price-alert", json={"threshold_price": 100}).status_code == 401
    assert client.get("/import/records").status_code == 401
    assert client.post("/catalog/sync").status_code == 401
    _register(client, "regular@example.com")
    assert client.get("/import/records").status_code == 403
    assert client.post("/catalog/sync").status_code == 403
    client.cookies.set(COOKIE_NAME, admin_token)
    assert client.get("/import/records").status_code == 200
    assert client.get("/catalog/sync/status").status_code == 200


def test_two_users_have_independent_personal_data(client, db_session):
    series = seed_catalog_series(db_session, "Multi User", "Auth Publisher", volumes=(1,))
    volume_id = series.volumes[0].id
    _, token_a = _register(client, "a@example.com")
    assert client.patch(f"/volume/{volume_id}/collection-status", json={"status": "owned"}).status_code == 200
    assert client.post(f"/volume/{volume_id}/wishlist", json={"user_id": 999}).status_code == 200
    assert client.put(f"/volume/{volume_id}/price-alert", json={"threshold_price": 100, "user_id": 999}).status_code == 200
    _, token_b = _register(client, "b@example.com")
    assert client.get(f"/volume/{volume_id}").json()["collection_status"] is None
    assert client.get(f"/volume/{volume_id}/wishlist").json()["wishlisted"] is False
    assert client.get(f"/volume/{volume_id}/price-alert").json()["alert"] is None
    assert client.delete(f"/volume/{volume_id}/wishlist").status_code == 200
    assert client.delete(f"/volume/{volume_id}/price-alert").status_code == 200
    assert client.patch(f"/volume/{volume_id}/collection-status", json={"status": "wanted", "user_id": 999}).json()["collection_status"] == "wanted"
    client.cookies.set(COOKIE_NAME, token_a)
    assert client.get(f"/volume/{volume_id}").json()["collection_status"] == "owned"
    assert client.get(f"/volume/{volume_id}/wishlist").json()["wishlisted"] is True
    assert client.get(f"/volume/{volume_id}/price-alert").json()["alert"]["threshold_price"] == 100
    assert db_session.scalar(select(UserVolumeCollection.user_id).where(UserVolumeCollection.status == "owned")) != 999
    assert db_session.scalar(select(WishlistItem.user_id)) != 999
    assert db_session.scalar(select(PriceAlert.user_id)) != 999
    client.cookies.set(COOKIE_NAME, token_b)
    assert client.get(f"/volume/{volume_id}").json()["collection_status"] == "wanted"


def test_catalog_volume_merge_keeps_personal_rows_or_blocks_conflict(db_session):
    series = seed_catalog_series(db_session, "Merge User Data", "Publisher", volumes=(1, 2))
    source, target = series.volumes
    db_session.add_all([
        UserVolumeCollection(user_id=1, volume_id=source.id, status="owned"),
        WishlistItem(user_id=1, volume_id=source.id),
        PriceAlert(user_id=1, volume_id=source.id, threshold_price=250),
    ])
    db_session.commit()
    CatalogSyncService(db_session)._move_personal_rows(source.id, target.id)
    db_session.commit()
    assert db_session.scalar(select(UserVolumeCollection.volume_id)) == target.id
    assert db_session.scalar(select(WishlistItem.volume_id)) == target.id
    assert db_session.scalar(select(PriceAlert.volume_id)) == target.id

    other = Volume(series_id=series.id, volume_number=3)
    db_session.add(other)
    db_session.flush()
    db_session.add(UserVolumeCollection(user_id=1, volume_id=other.id, status="wanted"))
    db_session.commit()
    with pytest.raises(ValueError, match="conflicting collection"):
        CatalogSyncService(db_session)._move_personal_rows(other.id, target.id)
    db_session.rollback()
    assert db_session.scalar(select(UserVolumeCollection.status).where(UserVolumeCollection.volume_id == other.id)) == "wanted"
