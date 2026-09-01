"""Rate limiting for the authentication endpoints.

`/api/auth/login` accepts a user's `api_key` in place of their password (see
docs/authentication.md: a Google-linked account has no password on this side).
That makes the api_key password-equivalent, and an unlimited login endpoint an
offline-speed guessing oracle against it. The same applies to `/api/auth/refresh`,
where a refresh token is the secret, and to `/api/auth/setup`, which is
unauthenticated by design until the first admin exists.

Only *failed* attempts count, and `/api/auth/login` is counted per account
rather than per caller. Both follow from how this endpoint is really used:
`/api/auth/login` is not only a login form, it is the password oracle LMS calls
on *every* Subsonic request (SubsonicResource.cpp -> PasswordServiceBase ->
MusicManagementPasswordService.cpp, which POSTs here and caches nothing). One
user opening their home screen therefore spends a dozen successful logins in a
second or two, and that server-to-server hop carries no X-Forwarded-For, so
`client_key` collapses to the LMS container's address for everybody. Counting
successes under a shared key let normal traffic exhaust the window, at which
point LMS read the 429 as "wrong password" (WrongUsernameOrPasswordError) and
every client logged itself out.

Guessing is still capped: a wrong password is a failure, ten of those against
one account within the window and that account stops answering. Spraying one
password across many accounts is what LMS's own LoginThrottler covers -- it
counts bad attempts per *real* client address, which is the dimension this side
of the hop cannot see.

Deliberately in-process and dependency-free: music-manager runs as a single
container (docker/docker-compose.yml), so a shared store would add a dependency
without buying anything. If it is ever scaled out, this needs to move to Redis --
per-process counters would then let an attacker multiply the limit by the number
of replicas.

Configuration:
    AUTH_RATE_LIMIT_ATTEMPTS         failed attempts per window (default 10)
    AUTH_RATE_LIMIT_WINDOW_SECONDS   window length in seconds (default 60)
    AUTH_RATE_LIMIT_ENABLED          set to 0/false to switch off
"""

import logging
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager

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

    Asking (`blocked`) and recording (`register_attempt`) are separate, so that
    reading the state of a key never fills it -- the callers here ask on every
    request but only record the ones that were rejected. Which attempts are
    worth recording is the caller's decision, not this class's.
    """

    def __init__(self, attempts: int, window_seconds: int):
        self.attempts = attempts
        self.window_seconds = window_seconds
        self._hits: dict[str, deque[float]] = defaultdict(deque)
        self._lock = threading.Lock()

    def blocked(self, key: str, now: float | None = None) -> tuple[bool, int]:
        """Report whether `key` has run out of attempts, without spending one.

        Returns (blocked, retry_after_seconds). `retry_after_seconds` is 0 while
        the key is still allowed through.
        """
        moment = time.monotonic() if now is None else now
        with self._lock:
            hits = self._expired_dropped(key, moment)
            if len(hits) >= self.attempts:
                return True, max(1, int(hits[0] + self.window_seconds - moment) + 1)
            return False, 0

    def register_attempt(self, key: str, now: float | None = None) -> None:
        """Record one attempt against `key`. What counts is the caller's call."""
        moment = time.monotonic() if now is None else now
        with self._lock:
            self._expired_dropped(key, moment).append(moment)

    def _expired_dropped(self, key: str, moment: float) -> deque[float]:
        """The key's attempts still inside the window. Caller holds the lock."""
        cutoff = moment - self.window_seconds
        hits = self._hits[key]
        while hits and hits[0] <= cutoff:
            hits.popleft()
        return hits

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


@contextmanager
def auth_attempt(request: Request, subject: str = '', count_successes: bool = False):
    """Guard one credential check: 429 up front, count it only if it was rejected.

    `subject` narrows the bucket to what is being guessed -- the account name on
    a login. Without it every account shares the caller's bucket, and since the
    caller is the LMS container for all of prod (see the module docstring), that
    is one bucket for the whole installation.

    A 401 or 403 raised inside the block is the rejection; anything else (a 200,
    a 500 from a database that is down) leaves the window untouched, unless
    `count_successes` says every call counts -- which is right for an endpoint
    with no legitimate repeat traffic to protect, such as first-time setup. The
    block is entered before credentials are evaluated, so an account that is
    already over its limit stops answering rather than staying a guessing oracle.
    """
    if not _enabled():
        yield
        return
    key = f'{request.url.path}|{client_key(request)}|{subject}'
    is_blocked, retry_after = auth_limiter.blocked(key)
    if is_blocked:
        logger.warning('Rate limit hit on %s by %s', request.url.path, client_key(request))
        raise HTTPException(
            status_code=429,
            detail='Too many attempts. Try again later.',
            headers={'Retry-After': str(retry_after)},
        )
    try:
        yield
    except HTTPException as exc:
        if count_successes or exc.status_code in (401, 403):
            auth_limiter.register_attempt(key)
        raise
    else:
        if count_successes:
            auth_limiter.register_attempt(key)
