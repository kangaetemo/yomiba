"""Small process-local login attempt limiter keyed by normalized email.

The direct peer IP may be the Next.js proxy, so X-Forwarded-For is ignored.
This protects one account from repeated guessing without treating every
proxied user as the same client. Exactly one backend process is required.
"""

from collections import deque
from threading import Lock
from time import monotonic


class LoginRateLimiter:
    def __init__(self, limit: int = 10, window_seconds: int = 300) -> None:
        self.limit = limit
        self.window_seconds = window_seconds
        self._attempts: dict[str, deque[float]] = {}
        self._lock = Lock()

    def check(self, key: str) -> int:
        """Count an attempt; return Retry-After seconds, or zero if allowed."""
        now = monotonic()
        with self._lock:
            if key not in self._attempts and len(self._attempts) >= 5000:
                self._attempts.pop(next(iter(self._attempts)))
            attempts = self._attempts.setdefault(key, deque())
            while attempts and attempts[0] <= now - self.window_seconds:
                attempts.popleft()
            if len(attempts) >= self.limit:
                return max(1, int(attempts[0] + self.window_seconds - now) + 1)
            attempts.append(now)
            return 0

    def clear(self, key: str) -> None:
        with self._lock:
            self._attempts.pop(key, None)
