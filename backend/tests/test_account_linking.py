"""Security review 2026-10-21, findings 1-3: an account opened with someone
else's address, Google e-mails Google is not authoritative for, and
registration / login abuse limits."""

import re
import threading

import pytest
from sqlalchemy import select

from app import auth as auth_core
from app.auth import COOKIE_NAME
from app.login_rate_limit import LoginRateLimiter
from app.models import EmailOutbox, EmailToken, User, UserVolumeCollection
from app.routes import auth as auth_routes
from app.services import account_mail
from app.utils import utcnow
from tests.test_account import PASSWORD, _claims, _register, _volume, google  # noqa: F401 - fixture

VICTIM = "kurban@gmail.com"


@pytest.fixture(autouse=True)
def mail_on(monkeypatch):
    """SMTP configured; mails are queued but never leave the test."""
    state = {"on": True}
    monkeypatch.setattr(account_mail, "enabled", lambda: state["on"])
    monkeypatch.setattr(account_mail, "send_now", lambda bind, ids: None)
    return state


def _token_from_mail(db_session, email, kind):
    db_session.expire_all()
    mail = db_session.scalars(select(EmailOutbox).where(EmailOutbox.to_email == email, EmailOutbox.kind == kind)
                              .order_by(EmailOutbox.id.desc())).first()
    assert mail is not None
    return re.search(r"/eposta-onay\?t=([\w-]+)", mail.body_text).group(1)


def _user(db_session, email):
    db_session.expire_all()
    return db_session.scalar(select(User).where(User.email == email))


# -- finding 1: pre-registered account ----------------------------------------------

def test_a_pre_registered_account_is_closed_to_its_creator_when_the_owner_signs_in_with_google(client, google):
    # The attacker registers the victim's address and keeps the session.
    assert _register(client, email=VICTIM, password="saldirgan1").status_code == 201
    attacker_cookie = client.cookies.get(COOKIE_NAME)
    # The real owner signs in with Google later.
    google["victim"] = _claims(sub="g-victim", email=VICTIM)
    client.cookies.clear()
    response = client.post("/auth/google", json={"credential": "victim"})
    assert response.status_code == 200
    assert response.json()["has_password"] is False and response.json()["notice"]
    assert client.get("/auth/me").status_code == 200
    # The attacker's old session and password no longer open the account.
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, attacker_cookie)
    assert client.get("/auth/me").status_code == 401
    client.cookies.clear()
    assert client.post("/auth/login", json={"email": VICTIM, "password": "saldirgan1"}).status_code == 401


def test_a_verified_account_keeps_its_password_and_sessions_when_google_is_linked(client, db_session, google):
    _register(client, email=VICTIM)
    own_cookie = client.cookies.get(COOKIE_NAME)
    token = _token_from_mail(db_session, VICTIM, "verify_email")
    assert client.post("/auth/email-token/confirm", json={"token": token}).json()["purpose"] == "verify"
    google["t"] = _claims(sub="g-1", email=VICTIM)
    client.cookies.clear()
    response = client.post("/auth/google", json={"credential": "t"})
    assert response.json()["has_password"] is True and response.json()["notice"] is None
    client.cookies.clear()
    client.cookies.set(COOKIE_NAME, own_cookie)
    assert client.get("/auth/me").json()["google"] is True


def test_registration_mails_a_verification_link_that_works_once(client, db_session):
    response = _register(client)
    assert response.json()["email_verified"] is False
    token = _token_from_mail(db_session, "okur@example.com", "verify_email")
    info = client.post("/auth/email-token", json={"token": token}).json()
    assert info == {"purpose": "verify", "email": "okur@example.com", "can_reject": True}
    assert client.post("/auth/email-token/confirm", json={"token": token}).status_code == 200
    assert client.get("/auth/me").json()["email_verified"] is True
    assert client.post("/auth/email-token/confirm", json={"token": token}).status_code == 400
    assert client.post("/auth/email-token", json={"token": "uydurma"}).status_code == 400


def test_a_resent_link_replaces_the_old_one_and_expired_links_fail(client, db_session):
    _register(client)
    first = _token_from_mail(db_session, "okur@example.com", "verify_email")
    assert client.post("/auth/verify-email/send").json() == {"sent": True}
    second = _token_from_mail(db_session, "okur@example.com", "verify_email")
    assert first != second
    assert client.post("/auth/email-token", json={"token": first}).status_code == 400
    for row in db_session.scalars(select(EmailToken)):
        row.expires_at = utcnow()
    db_session.commit()
    assert client.post("/auth/email-token", json={"token": second}).status_code == 400


def test_the_mailbox_owner_can_delete_an_account_someone_opened_with_their_address(client, db_session):
    _register(client, email=VICTIM, password="saldirgan1")
    vol = _volume(db_session)
    client.patch(f"/volume/{vol.id}/collection-status", json={"status": "owned"})
    token = _token_from_mail(db_session, VICTIM, "verify_email")
    client.cookies.clear()
    assert client.post("/auth/email-token/reject", json={"token": token}).status_code == 204
    assert _user(db_session, VICTIM) is None
    assert db_session.scalar(select(UserVolumeCollection.id)) is None
    # The address is free again.
    assert _register(client, email=VICTIM).status_code == 201


def test_a_verified_account_cannot_be_deleted_through_a_link(client, db_session):
    _register(client)
    token = _token_from_mail(db_session, "okur@example.com", "verify_email")
    # Verified some other way (e.g. Google) while this link is still valid.
    user = _user(db_session, "okur@example.com")
    user.email_verified_at = utcnow()
    db_session.commit()
    assert client.post("/auth/email-token", json={"token": token}).json()["can_reject"] is False
    assert client.post("/auth/email-token/reject", json={"token": token}).status_code == 400
    assert _user(db_session, "okur@example.com") is not None


# -- finding 2: Google is not authoritative for the address ------------------------

def test_a_non_gmail_google_account_is_not_linked_on_its_email_alone(client, db_session, google):
    _register(client)  # okur@example.com, has a password
    google["t"] = _claims(sub="g-1", email="okur@example.com")
    client.cookies.clear()
    response = client.post("/auth/google", json={"credential": "t"})
    assert response.status_code == 409
    assert response.json()["detail"]["code"] == "google_link_required"
    assert response.json()["detail"]["has_password"] is True
    assert _user(db_session, "okur@example.com").google_sub is None
    assert client.get("/auth/me").status_code == 401
    # A Workspace account for another domain proves nothing either.
    google["hd"] = _claims(sub="g-1", email="okur@example.com") | {"hd": "baska.com"}
    assert client.post("/auth/google", json={"credential": "hd"}).status_code == 409


def test_a_workspace_account_of_the_same_domain_is_linked(client, db_session, google):
    _register(client)
    google["t"] = _claims(sub="g-1", email="okur@example.com") | {"hd": "example.com"}
    client.cookies.clear()
    assert client.post("/auth/google", json={"credential": "t"}).json()["google"] is True


def test_linking_with_the_accounts_password(client, db_session, google):
    _register(client)
    google["t"] = _claims(sub="g-1", email="okur@example.com")
    client.cookies.clear()
    wrong = client.post("/auth/google/link", json={"credential": "t", "password": "yanlis-parola"})
    assert wrong.status_code == 400 and _user(db_session, "okur@example.com").google_sub is None
    response = client.post("/auth/google/link", json={"credential": "t", "password": PASSWORD})
    assert response.status_code == 200 and response.json()["google"] is True
    assert response.json()["has_password"] is True
    # From now on the Google account signs in by its id.
    client.cookies.clear()
    assert client.post("/auth/google", json={"credential": "t"}).status_code == 200


def test_password_linking_is_rate_limited(client, google):
    _register(client)
    google["t"] = _claims(sub="g-1", email="okur@example.com")
    client.cookies.clear()
    for _ in range(10):
        client.post("/auth/google/link", json={"credential": "t", "password": "yanlis-parola"})
    assert client.post("/auth/google/link", json={"credential": "t", "password": PASSWORD}).status_code == 429


def test_linking_through_a_mailed_link_proves_the_mailbox(client, db_session, google):
    assert _register(client, password="saldirgan1").status_code == 201
    attacker_cookie = client.cookies.get(COOKIE_NAME)
    google["t"] = _claims(sub="g-1", email="okur@example.com")
    client.cookies.clear()
    assert client.post("/auth/google/link-email", json={"credential": "t"}).json() == {"sent": True}
    token = _token_from_mail(db_session, "okur@example.com", "google_link")
    assert client.post("/auth/email-token", json={"token": token}).json()["purpose"] == "google_link"
    confirmed = client.post("/auth/email-token/confirm", json={"token": token}).json()
    assert confirmed["purpose"] == "google_link" and confirmed["notice"]
    user = _user(db_session, "okur@example.com")
    assert user.google_sub == "g-1" and user.password_hash is None and user.email_verified_at is not None
    # The unverified registration's session is gone; Google now signs in.
    client.cookies.set(COOKIE_NAME, attacker_cookie)
    assert client.get("/auth/me").status_code == 401
    client.cookies.clear()
    assert client.post("/auth/google", json={"credential": "t"}).status_code == 200
    assert client.post("/auth/email-token/confirm", json={"token": token}).status_code == 400


def test_link_mails_are_limited_per_account(client, google):
    _register(client)
    google["t"] = _claims(sub="g-1", email="okur@example.com")
    client.cookies.clear()
    for _ in range(3):
        assert client.post("/auth/google/link-email", json={"credential": "t"}).status_code == 200
    assert client.post("/auth/google/link-email", json={"credential": "t"}).status_code == 429


def test_a_google_account_linked_elsewhere_cannot_be_linked_again(client, google):
    _register(client)
    google["gmail"] = _claims(sub="g-1", email="baska@gmail.com")
    client.cookies.clear()
    client.post("/auth/google", json={"credential": "gmail"})
    google["t"] = _claims(sub="g-1", email="okur@example.com")
    client.cookies.clear()
    assert client.post("/auth/google/link", json={"credential": "t", "password": PASSWORD}).status_code == 409


def test_a_new_google_only_account_is_verified_only_for_gmail(client, google):
    google["g"] = _claims(sub="g-1", email="yeni@gmail.com")
    google["o"] = _claims(sub="g-2", email="yeni@example.com")
    client.cookies.clear()
    assert client.post("/auth/google", json={"credential": "g"}).json()["email_verified"] is True
    client.cookies.clear()
    assert client.post("/auth/google", json={"credential": "o"}).json()["email_verified"] is False


# -- finding 3: registration and login abuse ---------------------------------------

def test_registration_is_limited_per_client_before_any_password_is_hashed(client, monkeypatch):
    hashed = []
    real = auth_routes.hash_password
    monkeypatch.setattr(auth_routes, "hash_password", lambda raw: hashed.append(raw) or real(raw))
    headers = {"cf-connecting-ip": "203.0.113.7"}
    client.cookies.clear()
    for n in range(5):
        body = {"email": f"okur{n}@example.com", "password": PASSWORD, "display_name": "Okur"}
        assert client.post("/auth/register", json=body, headers=headers).status_code == 201
    body = {"email": "okur9@example.com", "password": PASSWORD, "display_name": "Okur"}
    response = client.post("/auth/register", json=body, headers=headers)
    assert response.status_code == 429 and "Retry-After" in response.headers
    assert len(hashed) == 5
    # Another client may still register.
    assert client.post("/auth/register", json=body, headers={"cf-connecting-ip": "203.0.113.8"}).status_code == 201


def test_registration_has_a_site_wide_ceiling_that_forged_addresses_do_not_escape(client):
    from app.login_rate_limit import RegistrationLimiter

    client.app.state.register_limiter = RegistrationLimiter(per_client=5, site=3)
    client.cookies.clear()
    for n in range(3):
        body = {"email": f"okur{n}@example.com", "password": PASSWORD, "display_name": "Okur"}
        assert client.post("/auth/register", json=body, headers={"cf-connecting-ip": f"10.0.0.{n}"}).status_code == 201
    body = {"email": "okur9@example.com", "password": PASSWORD, "display_name": "Okur"}
    assert client.post("/auth/register", json=body, headers={"cf-connecting-ip": "10.0.0.9"}).status_code == 429


def test_a_locked_account_stays_locked_when_the_limiter_fills_with_new_keys():
    limiter = LoginRateLimiter(limit=10, window_seconds=300, soft_cap=5000)
    for _ in range(10):
        limiter.record_failure("hedef@example.com")
    assert limiter.retry_after("hedef@example.com")
    for n in range(5000):
        limiter.record_failure(f"dolgu-{n}@example.com")
    assert limiter.retry_after("hedef@example.com")


def test_the_limiter_drops_expired_keys_to_make_room(monkeypatch):
    from app import login_rate_limit

    clock = [1000.0]
    monkeypatch.setattr(login_rate_limit, "monotonic", lambda: clock[0])
    limiter = LoginRateLimiter(limit=10, window_seconds=300, soft_cap=100)
    for n in range(100):
        limiter.record_failure(f"eski-{n}")
    clock[0] += 301
    limiter.record_failure("yeni")
    assert len(limiter._attempts) == 1


def test_password_hashing_answers_busy_when_every_slot_is_taken(client, monkeypatch):
    monkeypatch.setattr(auth_core, "_password_work", threading.BoundedSemaphore(1))
    monkeypatch.setattr(auth_core, "PASSWORD_WORK_WAIT_SECONDS", 0.01)
    auth_core._password_work.acquire()
    try:
        client.cookies.clear()
        response = _register(client)
        assert response.status_code == 503
    finally:
        auth_core._password_work.release()
    assert _register(client).status_code == 201


# -- no mail server yet ------------------------------------------------------------

def test_without_smtp_nothing_is_queued_and_mail_options_are_closed(client, db_session, google, mail_on):
    mail_on["on"] = False
    response = _register(client)
    assert response.status_code == 201 and response.json()["mail_enabled"] is False
    db_session.expire_all()
    assert db_session.scalar(select(EmailOutbox.id)) is None
    assert client.post("/auth/verify-email/send").status_code == 503
    google["t"] = _claims(sub="g-1", email="okur@example.com")
    client.cookies.clear()
    detail = client.post("/auth/google", json={"credential": "t"}).json()["detail"]
    assert detail["code"] == "google_link_required" and detail["can_email"] is False
    assert client.post("/auth/google/link-email", json={"credential": "t"}).status_code == 503
    # The password still links; Gmail still takes over an unverified account.
    assert client.post("/auth/google/link", json={"credential": "t", "password": PASSWORD}).status_code == 200
    _register(client, email=VICTIM, password="saldirgan1")
    google["v"] = _claims(sub="g-2", email=VICTIM)
    client.cookies.clear()
    assert client.post("/auth/google", json={"credential": "v"}).json()["has_password"] is False
