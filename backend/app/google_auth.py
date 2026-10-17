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
