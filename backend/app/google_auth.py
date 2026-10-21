"""Verify a "Sign in with Google" ID token (a JWT signed by Google).

The browser (and later the mobile apps) get the token from Google; the
backend checks it locally against Google's published keys — signature,
audience (our client ids), issuer, expiry — and that Google verified the
e-mail. No Google secret is stored. Keys are cached for an hour.
"""

from __future__ import annotations

import jwt

GOOGLE_ISSUERS = frozenset({"accounts.google.com", "https://accounts.google.com"})
JWKS_URL = "https://www.googleapis.com/oauth2/v3/certs"

_jwks = jwt.PyJWKClient(JWKS_URL, cache_keys=True, lifespan=3600, timeout=10)


class GoogleTokenError(ValueError):
    """The credential is not a valid Google ID token for us."""


def verify_google_credential(credential: str, client_ids: list[str]) -> dict:
    """The token's claims (``sub``, ``email``, ``name`` …) or GoogleTokenError."""
    if not credential or not client_ids:
        raise GoogleTokenError("missing credential or client id")
    try:
        key = _jwks.get_signing_key_from_jwt(credential)
        claims = jwt.decode(
            credential, key.key, algorithms=["RS256"], audience=client_ids, leeway=30,
            options={"require": ["exp", "iat", "iss", "sub", "aud"]},
        )
    except jwt.PyJWTError as exc:
        raise GoogleTokenError(str(exc)) from exc
    if claims.get("iss") not in GOOGLE_ISSUERS:
        raise GoogleTokenError("unexpected issuer")
    if not claims.get("email") or claims.get("email_verified") is not True:
        raise GoogleTokenError("e-mail not verified by Google")
    return claims


#: Addresses Google itself hosts: the Google account IS the mailbox.
GOOGLE_MAIL_DOMAINS = frozenset({"gmail.com", "googlemail.com"})


def google_owns_mailbox(claims: dict) -> bool:
    """True when Google is authoritative for the token's e-mail: a Gmail
    address, or a Google Workspace account (``hd`` claim) whose domain is the
    address's. For any other address ``email_verified`` only says the owner
    proved it once, when the Google account was made; the mailbox may have
    changed hands since, so it is no proof of who reads it now.
    https://developers.google.com/identity/gsi/web/guides/verify-google-id-token"""
    email = str(claims.get("email") or "").strip().lower()
    domain = email.rpartition("@")[2]
    if not domain:
        return False
    if domain in GOOGLE_MAIL_DOMAINS:
        return True
    hosted = str(claims.get("hd") or "").strip().lower()
    return bool(hosted) and hosted == domain
