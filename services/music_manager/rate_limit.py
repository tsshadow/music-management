"""Rate limiting for the authentication endpoints.

`/api/auth/login` accepts a user's `api_key` in place of their password (see
docs/authentication.md: a Google-linked account has no password on this side).
That makes the api_key password-equivalent, and an unlimited login endpoint an
offline-speed guessing oracle against it. The same applies to `/api/auth/refresh`,
where a refresh token is the secret, and to `/api/auth/setup`, which is
unauthenticated by design until the first admin exists.

Deliberately in-process and dependency-free: music-manager runs as a single
container (docker/docker-compose.yml), so a shared store would add a dependency
without buying anything. If it is ever scaled out, this needs to move to Redis --
per-process counters would then let an attacker multiply the limit by the number
of replicas.

Configuration:
    AUTH_RATE_LIMIT_ATTEMPTS         attempts per window (default 10)
    AUTH_RATE_LIMIT_WINDOW_SECONDS   window length in seconds (default 60)
    AUTH_RATE_LIMIT_ENABLED          set to 0/false to switch off
"""
import logging
import os
import threading
import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

logger = logging.getLogger('music-manager.rate-limit')

DEFAULT_ATTEMPTS = 10
DEFAULT_WINDOW_SECONDS = 60


def _int_env(name: str, default: int) -> int:
    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        logger.warning('Invalid %s, falling back to %d', name, default)
        return default
    return value if value > 0 else default


def _enabled() -> bool:
    return os.getenv('AUTH_RATE_LIMIT_ENABLED', '1').strip().lower() not in ('0', 'false', 'no')


class SlidingWindowRateLimiter:
    """Counts attempts per key over a moving window.

    A sliding window rather than a fixed one: with fixed buckets an attacker
    gets the full allowance twice in a row by straddling the boundary.
    """

    def __init__(self, attempts: int, window_seconds: int):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def check(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Register an attempt for `key`.

        Returns (allowed, retry_after_seconds). `retry_after_seconds` is 0 when
        the attempt was allowed.
        """
        moment = time.monotonic() if now is None else now
        cutoff = moment - self.window_seconds
        with self._lock:
            hits = self._hits[key]
            while hits and hits[0] <= cutoff:
                hits.popleft()
            if len(hits) >= self.attempts:
                return False, max(1, int(hits[0] + self.window_seconds - moment) + 1)
            hits.append(moment)
            return True, 0

    def reset(self, key: str | None = None) -> None:
        """Forget one key's history, or all of it. Used by the test suites."""
        with self._lock:
            if key is None:
                self._hits.clear()
            else:
                self._hits.pop(key, None)


auth_limiter = SlidingWindowRateLimiter(
    attempts=_int_env('AUTH_RATE_LIMIT_ATTEMPTS', DEFAULT_ATTEMPTS),
    window_seconds=_int_env('AUTH_RATE_LIMIT_WINDOW_SECONDS', DEFAULT_WINDOW_SECONDS),
)


def client_key(request: Request) -> str:
    """Identify the caller.

    Prefers the left-most X-Forwarded-For entry, because music-manager sits
    behind a reverse proxy in every deployment and request.client would
    otherwise be the proxy for everyone.
    """
    forwarded = request.headers.get('x-forwarded-for')
    if forwarded:
        return forwarded.split(',')[0].strip()
    return request.client.host if request.client else 'unknown'


def auth_rate_limit(request: Request) -> None:
    """FastAPI dependency: 429 once a caller exceeds the window."""
    if not _enabled():
        return
    allowed, retry_after = auth_limiter.check(client_key(request))
    if not allowed:
        logger.warning('Rate limit hit on %s by %s', request.url.path, client_key(request))
        raise HTTPException(
            status_code=429,
            detail='Too many attempts. Try again later.',
            headers={'Retry-After': str(retry_after)},
        )
