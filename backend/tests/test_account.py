"""Account features: Turkish validation, Google sign-in, sliding sessions,
profile / password changes, signing out other devices, deleting the account."""

from dataclasses import replace
from datetime import timedelta

import pytest
from sqlalchemy import select

from app.auth import COOKIE_NAME, token_digest
from app.config import get_settings
from app.google_auth import GoogleTokenError
from app.models import EmailOutbox, User, UserSession, UserVolumeCollection, Volume
from app.routes import auth as auth_routes
from app.utils import utcnow
from tests.test_import_service import seed_catalog_series

PASSWORD = "parola123"


def _register(client, email="okur@example.com", password=PASSWORD, name="Okur"):
    client.cookies.clear()
    return client.post("/auth/register", json={"email": email, "password": password, "display_name": name})


def _session_row(db_session, token):
    db_session.expire_all()
    return db_session.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))


def _naive(dt):
    return dt.replace(tzinfo=None)


def _volume(db_session):
    series = seed_catalog_series(db_session, "Berserk", "Gerekli Şeyler", volumes=(1,))
    vol = db_session.scalar(select(Volume).where(Volume.series_id == series.id))
    vol.catalog_present = vol.catalog_released = True
    db_session.commit()
    return vol


# -- registration messages ---------------------------------------------------------

def test_register_messages_are_turkish_and_eight_characters_are_enough(client):
    assert _register(client, email="not-an-email").json()["detail"] == "Geçerli bir e-posta adresi girin."
    assert _register(client, password="kisa123").json()["detail"] == "Parola en az 8 karakter olmalı."
    assert _register(client, name="   ").json()["detail"] == "Görünen ad boş olamaz."
    response = _register(client, password="sekizkar")
    assert response.status_code == 201
    assert response.json()["has_password"] is True and response.json()["google"] is False


# -- sliding sessions --------------------------------------------------------------

def test_a_used_session_is_extended_but_never_past_the_maximum(client, db_session):
    _register(client)
    token = client.cookies.get(COOKIE_NAME)
    row = _session_row(db_session, token)
    row.expires_at = utcnow() + timedelta(days=2)
    db_session.commit()
    assert client.get("/auth/me").status_code == 200
    assert _naive(_session_row(db_session, token).expires_at) > _naive(utcnow() + timedelta(days=29))
    # Logged in a year ago: no extension past the cap; it lapses.
    row = _session_row(db_session, token)
    row.created_at = utcnow() - timedelta(days=365)
    row.expires_at = utcnow() + timedelta(hours=1)
    db_session.commit()
    client.get("/auth/me")
    assert _naive(_session_row(db_session, token).expires_at) < _naive(utcnow() + timedelta(hours=2))


# -- Google ------------------------------------------------------------------------

@pytest.fixture()
def google(monkeypatch):
    """Google sign-in switched on; ``tokens`` maps a credential to its claims."""
    tokens: dict[str, dict] = {}
    monkeypatch.setattr(auth_routes, "get_settings", lambda: replace(get_settings(), google_client_ids=("web-client",)))

    def verify(credential, client_ids):
        assert client_ids == ["web-client"]
        if credential not in tokens:
            raise GoogleTokenError("bad signature")
        return tokens[credential]

    monkeypatch.setattr(auth_routes, "verify_google_credential", verify)
    return tokens


def _claims(sub="g-1", email="okur@example.com", name="Google Okur"):
    return {"sub": sub, "email": email, "email_verified": True, "name": name}


def test_google_creates_an_account_without_password(client, google):
    google["t1"] = _claims()
    client.cookies.clear()
    response = client.post("/auth/google", json={"credential": "t1"})
    assert response.status_code == 200, response.text
    assert response.json() | {"id": 0} == {"id": 0, "email": "okur@example.com", "display_name": "Google Okur",
                                           "role": "USER", "has_password": False, "google": True,
                                           "email_verified": False, "notice": None}
    assert client.get("/auth/me").status_code == 200
    # The password form never opens a Google-only account.
    client.cookies.clear()
    assert client.post("/auth/login", json={"email": "okur@example.com", "password": ""}).status_code == 401


def test_google_links_the_existing_account_and_keeps_its_collection(client, db_session, google):
    _register(client, email="okur@gmail.com")
    vol = _volume(db_session)
    assert client.patch(f"/volume/{vol.id}/collection-status", json={"status": "owned"}).status_code == 200
    google["t1"] = _claims(email="OKUR@gmail.com")
    client.cookies.clear()
    response = client.post("/auth/google", json={"credential": "t1"})
    # Gmail: Google owns the mailbox. The address was never verified, so the
    # registration's password is dropped (tests/test_account_linking.py).
    assert response.json()["google"] is True and response.json()["email_verified"] is True
    assert response.json()["has_password"] is False and response.json()["notice"]
    assert client.get("/me/collection").json()[0]["volume_id"] == vol.id
    # Another Google account claiming the same address is refused.
    google["t2"] = _claims(sub="g-2", email="okur@gmail.com")
    client.cookies.clear()
    assert client.post("/auth/google", json={"credential": "t2"}).status_code == 409


def test_google_refuses_bad_tokens_closed_accounts_and_when_off(client, db_session, google, monkeypatch):
    client.cookies.clear()
    assert client.post("/auth/google", json={"credential": "forged"}).status_code == 401
    db_session.add(User(email="kapali@example.com", password_hash=None, display_name="Eski", role="USER", is_active=False))
    db_session.commit()
    google["t1"] = _claims(email="kapali@example.com")
    assert client.post("/auth/google", json={"credential": "t1"}).status_code == 403
    monkeypatch.setattr(auth_routes, "get_settings", get_settings)
    assert client.post("/auth/google", json={"credential": "t1"}).json()["detail"] == "Google ile giriş henüz açık değil."


# -- profile, password, devices ----------------------------------------------------

def test_name_and_password_change_signs_other_devices_out(client, db_session):
    _register(client)
    other = client.cookies.get(COOKIE_NAME)
    client.cookies.clear()
    client.post("/auth/login", json={"email": "okur@example.com", "password": PASSWORD})
    here = client.cookies.get(COOKIE_NAME)
    assert client.patch("/auth/me", json={"display_name": "  Yeni   Ad "}).json()["display_name"] == "Yeni Ad"
    wrong = client.post("/auth/password", json={"current_password": "yanlis-parola", "new_password": "yeniparola1"})
    assert wrong.status_code == 400 and wrong.json()["detail"] == "Mevcut parola hatalı."
    assert client.post("/auth/password", json={"current_password": PASSWORD, "new_password": "yeniparola1"}).status_code == 200
    assert _session_row(db_session, other).revoked_at is not None
    assert _session_row(db_session, here).revoked_at is None
    client.cookies.clear()
    assert client.post("/auth/login", json={"email": "okur@example.com", "password": "yeniparola1"}).status_code == 200


def test_google_only_account_sets_a_password_without_the_current_one(client, google):
    google["t1"] = _claims()
    client.cookies.clear()
    client.post("/auth/google", json={"credential": "t1"})
    assert client.post("/auth/password", json={"new_password": "yeniparola1"}).json()["has_password"] is True


def test_logout_others_keeps_this_device(client, db_session):
    _register(client)
    other = client.cookies.get(COOKIE_NAME)
    client.cookies.clear()
    client.post("/auth/login", json={"email": "okur@example.com", "password": PASSWORD})
    assert client.post("/auth/logout-others").json() == {"revoked": 1}
    assert _session_row(db_session, other).revoked_at is not None
    assert client.get("/auth/me").status_code == 200


# -- deleting the account ----------------------------------------------------------

def test_delete_account_removes_everything_personal(client, db_session):
    _register(client)
    user_id = client.get("/auth/me").json()["id"]
    vol = _volume(db_session)
    db_session.add(EmailOutbox(to_email="okur@example.com", subject="s", body_text="b", kind="price_alert", ref="r1"))
    db_session.commit()
    client.patch(f"/volume/{vol.id}/collection-status", json={"status": "owned"})
    assert client.post("/auth/delete", json={"confirm": "yanlis"}).json()["detail"] == "Parola hatalı."
    assert client.post("/auth/delete", json={"confirm": PASSWORD}).status_code == 204
    db_session.expire_all()
    assert db_session.get(User, user_id) is None
    assert db_session.scalar(select(UserVolumeCollection.id)) is None
    assert db_session.scalar(select(EmailOutbox.id)) is None
    assert client.get("/auth/me").status_code == 401


def test_google_only_account_confirms_deletion_with_its_email_and_admins_cannot(client, db_session, google):
    google["t1"] = _claims()
    client.cookies.clear()
    client.post("/auth/google", json={"credential": "t1"})
    assert client.post("/auth/delete", json={"confirm": "baska@example.com"}).json()["detail"] == "Onay hatalı."
    assert client.post("/auth/delete", json={"confirm": " OKUR@example.com "}).status_code == 204
    _register(client, email="yonetici@example.com")
    admin = db_session.scalar(select(User).where(User.email == "yonetici@example.com"))
    admin.role = "ADMIN"
    db_session.commit()
    assert client.post("/auth/delete", json={"confirm": PASSWORD}).status_code == 400


def test_my_lists_carry_the_series_volume_count(client, db_session):
    """Koleksiyonum's "2 / 3 cilt" progress: released numbered volumes only."""
    _register(client)
    series = seed_catalog_series(db_session, "Berserk", "Gerekli Şeyler", volumes=(1, 2, 3, 4))
    vols = {v.volume_number: v for v in db_session.scalars(select(Volume).where(Volume.series_id == series.id))}
    for n, v in vols.items():
        v.catalog_present = True
        v.catalog_released = n != 4  # announced, not out yet
    db_session.commit()
    client.patch(f"/volume/{vols[1].id}/collection-status", json={"status": "owned"})
    item = client.get("/me/collection").json()[0]
    assert item["series_volume_count"] == 3
