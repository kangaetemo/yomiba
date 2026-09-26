"""Small process-local login attempt limiter keyed by normalized email.

The direct peer IP may be the Next.js proxy, so X-Forwarded-For is ignored
(it is spoofable and must not decide authentication). This protects one
account from repeated guessing without treating every proxied user as the
same client. Exactly one backend process is required.

Targeted lockout (M6): anyone can lock an account by failing its login.
A browser that has logged in to that account before carries a signed
"trusted device" cookie; while the account is locked, such a browser is
limited per device instead of per account, so the real owner can still log
in. An attacker cannot forge the cookie (HMAC with a server secret) and gets
no bypass. Only FAILED attempts are counted.
"""

from __future__ import annotations

import hashlib
import hmac
import logging
import os
import secrets
import time
from collections import deque
from threading import Lock
from time import monotonic

logger = logging.getLogger("yomiba.auth")

DEVICE_COOKIE_NAME = "yomiba_device"
DEVICE_COOKIE_DAYS = 180


class LoginRateLimiter:
    def __init__(self, limit: int = 10, window_seconds: int = 300) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def _prune(self, key: str, now: float) -> deque[float]:
        if key not in self._attempts and len(self._attempts) >= 5000:
            self._attempts.pop(next(iter(self._attempts)))
        attempts = self._attempts.setdefault(key, deque())
        while attempts and attempts[0] <= now - self.window_seconds:
            attempts.popleft()
        return attempts

    def retry_after(self, key: str) -> int:
        """Seconds until ``key`` may try again; zero when allowed. Does not
        count an attempt."""
        now = monotonic()
        with self._lock:
            attempts = self._prune(key, now)
            if len(attempts) >= self.limit:
                return max(1, int(attempts[0] + self.window_seconds - now) + 1)
            return 0

    def record_failure(self, key: str) -> None:
        with self._lock:
            self._prune(key, monotonic()).append(monotonic())

    def check(self, key: str) -> int:
        """Backward-compatible: count an attempt; return Retry-After seconds,
        or zero if allowed."""
        retry = self.retry_after(key)
        if not retry:
            self.record_failure(key)
        return retry

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)


def _device_secret() -> bytes:
    configured = os.getenv("AUTH_DEVICE_SECRET", "").strip()
    if configured:
        return configured.encode("utf-8")
    logger.warning(
        "AUTH_DEVICE_SECRET is not set; trusted-device cookies are only valid "
        "until the backend process restarts"
    )
    return secrets.token_bytes(32)


_SECRET = _device_secret()


def _sign(payload: str) -> str:
    return hmac.new(_SECRET, payload.encode("utf-8"), hashlib.sha256).hexdigest()


def issue_device_token(user_id: int) -> str:
    expires = int(time.time()) + DEVICE_COOKIE_DAYS * 86400
    payload = f"{user_id}.{expires}"
    return f"{payload}.{_sign(payload)}"


def device_user_id(token: str | None) -> int | None:
    """User id of a valid, unexpired trusted-device token, else None."""
    if not token:
        return None
    parts = token.split(".")
    if len(parts) != 3 or not parts[0].isdigit() or not parts[1].isdigit():
        return None
    payload = f"{parts[0]}.{parts[1]}"
    if not hmac.compare_digest(_sign(payload), parts[2]):
        return None
    if int(parts[1]) < time.time():
        return None
    return int(parts[0])


def device_key(token: str) -> str:
    return "device:" + hashlib.sha256(token.encode("utf-8")).hexdigest()
