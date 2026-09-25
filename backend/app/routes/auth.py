"""Register, log in and revoke opaque server-side sessions."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import COOKIE_NAME, PASSWORD_HASHER, _lookup_session, new_session, require_user, verify_password
from ..config import get_settings
from ..database import get_db
from ..models import User
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
    return _public(user)


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, request: Request, session: Session = Depends(get_db)) -> UserOut:
    email = str(payload.email).strip().lower()
    retry_after = request.app.state.login_limiter.check(email)
    if retry_after:
        raise HTTPException(status_code=429, detail="Çok fazla giriş denemesi.", headers={"Retry-After": str(retry_after)})
    user = session.scalar(select(User).where(User.email == email))
    if not verify_password(payload.password, user.password_hash if user and user.is_active else None):
        raise HTTPException(status_code=401, detail="E-posta veya parola hatalı.")
    assert user is not None
    request.app.state.login_limiter.clear(email)
    _set_cookie(response, new_session(session, user))
    return _public(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_db)) -> None:
    _, login_session = _lookup_session(request, session)
    if login_session is not None:
        login_session.revoked_at = utcnow()
        session.commit()
    response.delete_cookie(COOKIE_NAME, path="/")


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)) -> UserOut:
    return _public(user)
