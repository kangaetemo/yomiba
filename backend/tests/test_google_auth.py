"""verify_google_credential with real RS256 signatures (a local key stands in
for Google's published one)."""

import time
from types import SimpleNamespace

import jwt
import pytest
from cryptography.hazmat.primitives.asymmetric import rsa

from app import google_auth
from app.google_auth import GoogleTokenError, verify_google_credential

KEY = rsa.generate_private_key(public_exponent=65537, key_size=2048)
OTHER = rsa.generate_private_key(public_exponent=65537, key_size=2048)


@pytest.fixture(autouse=True)
def google_keys(monkeypatch):
    monkeypatch.setattr(google_auth._jwks, "get_signing_key_from_jwt",
                        lambda token: SimpleNamespace(key=KEY.public_key()))


def token(key=KEY, **overrides):
    now = int(time.time())
    claims = {"iss": "https://accounts.google.com", "aud": "web-client", "sub": "123", "iat": now,
              "exp": now + 600, "email": "okur@example.com", "email_verified": True} | overrides
    return jwt.encode({k: v for k, v in claims.items() if v is not None}, key, algorithm="RS256")


def test_a_valid_google_token_gives_its_claims():
    assert verify_google_credential(token(), ["web-client"])["sub"] == "123"
    assert verify_google_credential(token(iss="accounts.google.com"), ["mobile", "web-client"])["email"] == "okur@example.com"


@pytest.mark.parametrize("bad", [
    {"key": OTHER},                       # not signed by Google
    {"aud": "someone-else"},              # issued to another app
    {"iss": "https://evil.example"},
    {"exp": int(time.time()) - 3600},     # expired
    {"email_verified": False},
    {"email": None},
])
def test_invalid_google_tokens_are_refused(bad):
    key = bad.pop("key", KEY)
    with pytest.raises(GoogleTokenError):
        verify_google_credential(token(key=key, **bad), ["web-client"])


def test_nothing_is_accepted_without_a_client_id():
    with pytest.raises(GoogleTokenError):
        verify_google_credential(token(), [])
