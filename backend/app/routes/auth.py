"""Register, log in and revoke opaque server-side sessions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import COOKIE_NAME, PASSWORD_HASHER, _lookup_session, new_session, require_user, verify_password
from ..config import get_settings
from ..database import get_db
from ..login_rate_limit import (
    DEVICE_COOKIE_DAYS,
    DEVICE_COOKIE_NAME,
    device_key,
    device_user_id,
    issue_device_token,
)
from ..models import User, UserSession
from ..utils import utcnow

router = APIRouter(prefix="/auth", tags=["auth"])


class RegisterIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=12, max_length=128)
    display_name: str = Field(min_length=1, max_length=100)


class LoginIn(BaseModel):
    email: EmailStr
    password: str


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str


def _public(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, role=user.role)


def _set_cookie(response: Response, token: str) -> None:
    settings = get_settings()
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=settings.auth_cookie_secure,
        samesite="lax", path="/", max_age=settings.auth_session_days * 86400,
    )


def _set_device_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        DEVICE_COOKIE_NAME, issue_device_token(user.id), httponly=True,
        secure=get_settings().auth_cookie_secure, samesite="lax", path="/",
        max_age=DEVICE_COOKIE_DAYS * 86400,
    )


def _purge_expired_sessions(session: Session, user: User) -> None:
    session.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id,
            (UserSession.expires_at <= utcnow()) | UserSession.revoked_at.isnot(None),
        )
    )


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn, response: Response, session: Session = Depends(get_db)) -> UserOut:
    email = str(payload.email).strip().lower()
    name = payload.display_name.strip()
    if not name:
        raise HTTPException(status_code=422, detail="Görünen ad boş olamaz.")
    user = User(email=email, password_hash=PASSWORD_HASHER.hash(payload.password), display_name=name, role="USER")
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Bu e-posta kullanılamıyor.") from exc
    token = new_session(session, user)
    _set_cookie(response, token)
    _set_device_cookie(response, user)
    return _public(user)


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, request: Request, session: Session = Depends(get_db)) -> UserOut:
    email = str(payload.email).strip().lower()
    limiter = request.app.state.login_limiter
    user = session.scalar(select(User).where(User.email == email))
    # Account-wide limit (X-Forwarded-For is never trusted). While the
    # account is locked, a browser holding a valid trusted-device cookie for
    # THIS account is limited per device instead, so a third party cannot
    # lock the real owner out.
    limit_key = email
    retry_after = limiter.retry_after(email)
    device_token = request.cookies.get(DEVICE_COOKIE_NAME)
    if retry_after and user is not None and device_user_id(device_token) == user.id:
        limit_key = device_key(device_token)
        retry_after = limiter.retry_after(limit_key)
    if retry_after:
        raise HTTPException(status_code=429, detail="Çok fazla giriş denemesi.", headers={"Retry-After": str(retry_after)})
    if not verify_password(payload.password, user.password_hash if user and user.is_active else None):
        limiter.record_failure(limit_key)
        raise HTTPException(status_code=401, detail="E-posta veya parola hatalı.")
    assert user is not None
    limiter.clear(email)
    if limit_key != email:
        limiter.clear(limit_key)
    _purge_expired_sessions(session, user)
    _set_cookie(response, new_session(session, user))
    _set_device_cookie(response, user)
    return _public(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_db)) -> None:
    _, login_session = _lookup_session(request, session)
    if login_session is not None:
        login_session.revoked_at = utcnow()
        session.commit()
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True,
        secure=get_settings().auth_cookie_secure, samesite="lax",
    )


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)) -> UserOut:
    return _public(user)
