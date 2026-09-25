"""Session authentication and reusable authorization dependencies."""

from __future__ import annotations

import hashlib
import secrets
from datetime import timedelta, timezone

from argon2 import PasswordHasher, Type
from argon2.exceptions import VerifyMismatchError, VerificationError
from fastapi import Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from .config import get_settings
from .database import get_db
from .models import User, UserSession
from .utils import utcnow

COOKIE_NAME = "yomiba_session"
PASSWORD_HASHER = PasswordHasher(type=Type.ID)
# Keep a real Argon2 verification on missing accounts to avoid a trivial timing oracle.
DUMMY_HASH = PASSWORD_HASHER.hash("not-a-real-account-password")


def token_digest(token: str) -> str:
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


def new_session(session: Session, user: User) -> str:
    token = secrets.token_urlsafe(32)
    session.add(UserSession(
        user_id=user.id,
        token_hash=token_digest(token),
        expires_at=utcnow() + timedelta(days=get_settings().auth_session_days),
    ))
    session.commit()
    return token


def _lookup_session(request: Request, session: Session) -> tuple[User | None, UserSession | None]:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None, None
    row = session.scalar(select(UserSession).where(UserSession.token_hash == token_digest(token)))
    if row is None or row.revoked_at is not None:
        return None, None
    expires = row.expires_at.replace(tzinfo=row.expires_at.tzinfo or timezone.utc)
    if expires <= utcnow():
        return None, None
    user = session.get(User, row.user_id)
    if user is None or not user.is_active:
        return None, None
    return user, row


def optional_user(request: Request, session: Session = Depends(get_db)) -> User | None:
    return _lookup_session(request, session)[0]


def require_user(user: User | None = Depends(optional_user)) -> User:
    if user is None:
        raise HTTPException(status_code=401, detail="Giriş yapmanız gerekiyor.")
    return user


def require_admin(user: User = Depends(require_user)) -> User:
    if user.role != "ADMIN":
        raise HTTPException(status_code=403, detail="Yönetici yetkisi gerekiyor.")
    return user


def verify_password(password: str, stored: str | None) -> bool:
    try:
        if stored is None:
            PASSWORD_HASHER.verify(DUMMY_HASH, password)
            return False
        return PASSWORD_HASHER.verify(stored, password)
    except (VerifyMismatchError, VerificationError):
        return False
