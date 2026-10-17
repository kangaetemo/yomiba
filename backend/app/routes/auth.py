"""Register, log in (password or Google), manage and delete the account.

Sessions are opaque server-side rows (see ``app.auth``). Every message a
reader can see is Turkish, so the request bodies are plain strings checked
here rather than by pydantic constraints (whose messages are English).
"""

from __future__ import annotations

import logging

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel
from sqlalchemy import delete, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ..auth import (
    COOKIE_MAX_AGE_DAYS,
    COOKIE_NAME,
    PASSWORD_HASHER,
    _lookup_session,
    new_session,
    require_user,
    verify_password,
)
from ..config import get_settings
from ..database import get_db
from ..google_auth import GoogleTokenError, verify_google_credential
from ..login_rate_limit import (
    DEVICE_COOKIE_DAYS,
    DEVICE_COOKIE_NAME,
    device_key,
    device_user_id,
    issue_device_token,
)
from ..models import EmailOutbox, PriceAlert, User, UserSession, UserVolumeCollection, WishlistItem
from ..utils import utcnow

logger = logging.getLogger("yomiba.auth")
router = APIRouter(prefix="/auth", tags=["auth"])

PASSWORD_MIN = 8
PASSWORD_MAX = 128
NAME_MAX = 100


class RegisterIn(BaseModel):
    email: str = ""
    password: str = ""
    display_name: str = ""


class LoginIn(BaseModel):
    email: str = ""
    password: str = ""


class GoogleIn(BaseModel):
    credential: str = ""


class ProfileIn(BaseModel):
    display_name: str = ""


class PasswordIn(BaseModel):
    #: Required when the account already has a password.
    current_password: str = ""
    new_password: str = ""


class DeleteIn(BaseModel):
    #: The account's password, or (Google-only accounts) its e-mail address.
    confirm: str = ""


class UserOut(BaseModel):
    id: int
    email: str
    display_name: str
    role: str
    has_password: bool
    google: bool


def _public(user: User) -> UserOut:
    return UserOut(id=user.id, email=user.email, display_name=user.display_name, role=user.role,
                   has_password=user.password_hash is not None, google=user.google_sub is not None)


def _bad(detail: str, status: int = 422) -> HTTPException:
    return HTTPException(status_code=status, detail=detail)


def _clean_email(raw: str) -> str:
    try:
        return validate_email(raw.strip(), check_deliverability=False).normalized.lower()
    except EmailNotValidError as exc:
        raise _bad("Geçerli bir e-posta adresi girin.") from exc


def _clean_name(raw: str) -> str:
    name = " ".join(raw.split())
    if not name:
        raise _bad("Görünen ad boş olamaz.")
    if len(name) > NAME_MAX:
        raise _bad(f"Görünen ad en fazla {NAME_MAX} karakter olabilir.")
    return name


def _check_password(raw: str) -> str:
    if len(raw) < PASSWORD_MIN:
        raise _bad(f"Parola en az {PASSWORD_MIN} karakter olmalı.")
    if len(raw) > PASSWORD_MAX:
        raise _bad(f"Parola en fazla {PASSWORD_MAX} karakter olabilir.")
    return raw


def _set_cookie(response: Response, token: str) -> None:
    response.set_cookie(
        COOKIE_NAME, token, httponly=True, secure=get_settings().auth_cookie_secure,
        samesite="lax", path="/", max_age=COOKIE_MAX_AGE_DAYS * 86400,
    )


def _set_device_cookie(response: Response, user: User) -> None:
    response.set_cookie(
        DEVICE_COOKIE_NAME, issue_device_token(user.id), httponly=True,
        secure=get_settings().auth_cookie_secure, samesite="lax", path="/",
        max_age=DEVICE_COOKIE_DAYS * 86400,
    )


def _clear_cookie(response: Response) -> None:
    response.delete_cookie(
        COOKIE_NAME, path="/", httponly=True,
        secure=get_settings().auth_cookie_secure, samesite="lax",
    )


def _purge_expired_sessions(session: Session, user: User) -> None:
    session.execute(
        delete(UserSession).where(
            UserSession.user_id == user.id,
            (UserSession.expires_at <= utcnow()) | UserSession.revoked_at.isnot(None),
        )
    )


def _start_session(session: Session, response: Response, user: User) -> None:
    _purge_expired_sessions(session, user)
    _set_cookie(response, new_session(session, user))
    _set_device_cookie(response, user)


def _revoke_others(session: Session, user: User, keep: UserSession | None) -> int:
    rows = list(session.scalars(select(UserSession).where(
        UserSession.user_id == user.id, UserSession.revoked_at.is_(None))))
    now = utcnow()
    count = 0
    for row in rows:
        if keep is None or row.id != keep.id:
            row.revoked_at = now
            count += 1
    return count


@router.post("/register", response_model=UserOut, status_code=201)
def register(payload: RegisterIn, response: Response, session: Session = Depends(get_db)) -> UserOut:
    email = _clean_email(payload.email)
    name = _clean_name(payload.display_name)
    password = _check_password(payload.password)
    user = User(email=email, password_hash=PASSWORD_HASHER.hash(password), display_name=name, role="USER")
    session.add(user)
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Bu e-posta kullanılamıyor.") from exc
    _start_session(session, response, user)
    return _public(user)


@router.post("/login", response_model=UserOut)
def login(payload: LoginIn, response: Response, request: Request, session: Session = Depends(get_db)) -> UserOut:
    email = payload.email.strip().lower()
    limiter = request.app.state.login_limiter
    user = session.scalar(select(User).where(User.email == email)) if email else None
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
        raise HTTPException(status_code=429, detail="Çok fazla giriş denemesi. Biraz sonra tekrar deneyin.",
                            headers={"Retry-After": str(retry_after)})
    if not verify_password(payload.password, user.password_hash if user and user.is_active else None):
        limiter.record_failure(limit_key)
        raise HTTPException(status_code=401, detail="E-posta veya parola hatalı.")
    assert user is not None
    limiter.clear(email)
    if limit_key != email:
        limiter.clear(limit_key)
    _start_session(session, response, user)
    return _public(user)


@router.post("/google", response_model=UserOut)
def google_login(payload: GoogleIn, response: Response, session: Session = Depends(get_db)) -> UserOut:
    """Sign in (or up) with a Google ID token. A Yomiba account with the same
    e-mail is linked automatically: Google has verified the address."""
    client_ids = list(get_settings().google_client_ids)
    if not client_ids:
        raise HTTPException(status_code=503, detail="Google ile giriş henüz açık değil.")
    try:
        claims = verify_google_credential(payload.credential, client_ids)
    except GoogleTokenError as exc:
        logger.info("google sign-in rejected: %s", exc)
        raise HTTPException(status_code=401, detail="Google girişi doğrulanamadı. Tekrar deneyin.") from exc
    sub = str(claims["sub"])
    email = str(claims["email"]).strip().lower()
    user = session.scalar(select(User).where(User.google_sub == sub))
    if user is None:
        user = session.scalar(select(User).where(User.email == email))
        if user is not None:
            if user.google_sub not in (None, sub):
                raise HTTPException(status_code=409, detail="Bu e-posta başka bir Google hesabına bağlı.")
            user.google_sub = sub
            user.updated_at = utcnow()
        else:
            name = " ".join(str(claims.get("name") or "").split())[:NAME_MAX] or email.split("@")[0][:NAME_MAX]
            # is_active explicitly: the column default applies only at INSERT.
            user = User(email=email, password_hash=None, display_name=name, role="USER",
                        google_sub=sub, is_active=True)
            session.add(user)
    if not user.is_active:
        session.rollback()
        raise HTTPException(status_code=403, detail="Bu hesap kapalı.")
    try:
        session.commit()
    except IntegrityError as exc:
        session.rollback()
        raise HTTPException(status_code=409, detail="Bu e-posta kullanılamıyor.") from exc
    _start_session(session, response, user)
    return _public(user)


@router.post("/logout", status_code=204)
def logout(request: Request, response: Response, session: Session = Depends(get_db)) -> None:
    _, login_session = _lookup_session(request, session)
    if login_session is not None:
        login_session.revoked_at = utcnow()
        session.commit()
    _clear_cookie(response)


@router.get("/me", response_model=UserOut)
def me(user: User = Depends(require_user)) -> UserOut:
    return _public(user)


@router.patch("/me", response_model=UserOut)
def update_profile(payload: ProfileIn, user: User = Depends(require_user), session: Session = Depends(get_db)) -> UserOut:
    user.display_name = _clean_name(payload.display_name)
    user.updated_at = utcnow()
    session.commit()
    return _public(user)


@router.post("/password", response_model=UserOut)
def change_password(payload: PasswordIn, request: Request, user: User = Depends(require_user),
                    session: Session = Depends(get_db)) -> UserOut:
    """Change the password (or set one on a Google-only account). Signs every
    other device out."""
    limiter = request.app.state.login_limiter
    key = f"password:{user.id}"
    if user.password_hash is not None:
        if limiter.retry_after(key):
            raise HTTPException(status_code=429, detail="Çok fazla deneme. Biraz sonra tekrar deneyin.")
        if not verify_password(payload.current_password, user.password_hash):
            limiter.record_failure(key)
            raise _bad("Mevcut parola hatalı.", 400)
        limiter.clear(key)
    user.password_hash = PASSWORD_HASHER.hash(_check_password(payload.new_password))
    user.updated_at = utcnow()
    _, current = _lookup_session(request, session)
    _revoke_others(session, user, current)
    session.commit()
    return _public(user)


@router.post("/logout-others")
def logout_others(request: Request, user: User = Depends(require_user), session: Session = Depends(get_db)) -> dict:
    """Sign out every other browser / device; this one stays signed in."""
    _, current = _lookup_session(request, session)
    count = _revoke_others(session, user, current)
    session.commit()
    return {"revoked": count}


@router.post("/delete", status_code=204)
def delete_account(payload: DeleteIn, request: Request, response: Response,
                   user: User = Depends(require_user), session: Session = Depends(get_db)) -> None:
    """Delete the account and everything personal: collection, wishlist,
    price alerts, sessions and unsent alert mails. Confirmed with the
    password, or the e-mail address on a Google-only account."""
    if user.role == "ADMIN":
        raise _bad("Yönetici hesabı buradan silinemez.", 400)
    limiter = request.app.state.login_limiter
    key = f"delete:{user.id}"
    if limiter.retry_after(key):
        raise HTTPException(status_code=429, detail="Çok fazla deneme. Biraz sonra tekrar deneyin.")
    if user.password_hash is not None:
        confirmed = verify_password(payload.confirm, user.password_hash)
    else:
        confirmed = payload.confirm.strip().lower() == user.email
    if not confirmed:
        limiter.record_failure(key)
        raise _bad("Onay hatalı." if user.password_hash is None else "Parola hatalı.", 400)
    email = user.email
    for model in (UserVolumeCollection, WishlistItem, PriceAlert, UserSession):
        session.execute(delete(model).where(model.user_id == user.id))
    session.execute(delete(EmailOutbox).where(EmailOutbox.to_email == email, EmailOutbox.sent_at.is_(None)))
    session.delete(user)
    session.commit()
    logger.info("account %s deleted by its owner", user.id)
    _clear_cookie(response)
