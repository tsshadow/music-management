"""Rate limiting for the authentication endpoints.

`/api/auth/login` accepts a user's `api_key` in place of their password (see
docs/authentication.md: a Google-linked account has no password on this side).
That makes the api_key password-equivalent, and an unlimited login endpoint an
offline-speed guessing oracle against it. The same applies to `/api/auth/refresh`,
where a refresh token is the secret, and to `/api/auth/setup`, which is
unauthenticated by design until the first admin exists.

Only *failed* attempts count. Successes are free because of how this endpoint
is really used: `/api/auth/login` is not only a login form, it is the password
oracle LMS calls on *every* Subsonic request (SubsonicResource.cpp ->
PasswordServiceBase -> MusicManagementPasswordService.cpp, which POSTs here and
caches nothing). One user opening their home screen spends a dozen successful
logins in a second or two; counting those let normal traffic exhaust the window,
at which point LMS read the 429 as "wrong password" and every client logged
itself out.

Who the caller is
-----------------
`client_key` names the caller by address. The TCP peer is almost never the
client: every login arrives through a proxy -- the nginx in front of
the web-player host (/muma/api/auth/login), or LMS itself for everything on
the LMS host, whose password checks and proxied logins are made from the LMS
container. So an X-Forwarded-For header is read, but only when whoever wrote it
can be believed:

* The peer is on a trusted network (``AUTH_TRUSTED_PROXIES``, by default
  loopback and the networks this container is attached to -- the Docker
  bridge that nginx and LMS reach it over), or the request carries the system
  key (LMS's password checks do). A LAN address is not trusted: port 8000 is
  published on the host's loopback only (issue #218), so a LAN caller that
  reaches the app anyway is keyed on its own address.
* The chain is then walked from the right, skipping trusted addresses, and the
  first address that is not a proxy is the client -- nginx's
  `real_ip_recursive`. The left-most entry is whatever the client typed; it
  used to be taken at its word, so a caller could start a fresh bucket with
  every guess.
* A peer that is neither gets its header ignored: an internet caller reaching
  port 8000 directly is keyed on its own address, whatever it claims.

LMS sends the address it resolved itself as the only entry, never the client's
own header (MusicManagementPasswordService.cpp, MumaResource.cpp). Until LMS
did, every login through lms.<domain> reached this side as the LMS container
and could only be limited per account
(docs/bug-reports/079-google-login-unverified-email-and-lms-login-limit.md).

Buckets
-------
A login is counted twice, and refused when either is full:

* per client *and* account (``AUTH_RATE_LIMIT_ATTEMPTS``, default 10): one
  guesser is stopped quickly, and a phone stuck on a stale password locks only
  itself out, not the account for everyone else;
* per account from anywhere (``AUTH_RATE_LIMIT_ACCOUNT_ATTEMPTS``, default 50):
  guessing spread over many addresses still meets a ceiling. It sits above the
  per-client limit so that a single noisy client cannot reach it on its own.

The other endpoints (refresh, setup) have no account to name and are counted
per client only.

Deliberately in-process and dependency-free: music-manager runs as a single
container (docker/docker-compose.yml), so a shared store would add a dependency
without buying anything. If it is ever scaled out, this needs to move to Redis --
per-process counters would then let an attacker multiply the limit by the number
of replicas.

Configuration:
    AUTH_RATE_LIMIT_ATTEMPTS          failed attempts per client (and account) per window (default 10)
    AUTH_RATE_LIMIT_ACCOUNT_ATTEMPTS  failed attempts per account from anywhere per window (default 50)
    AUTH_RATE_LIMIT_WINDOW_SECONDS    window length in seconds (default 60)
    AUTH_RATE_LIMIT_ENABLED           set to 0/false to switch off
    AUTH_TRUSTED_PROXIES              comma-separated networks whose X-Forwarded-For is
                                      believed (default loopback + `connected`). The word
                                      `connected` stands for every IPv4 network the process
                                      reaches without a gateway: inside the container, its
                                      Docker networks.
"""

import ipaddress
import logging
import os
import threading
import time
from collections import defaultdict, deque
from contextlib import contextmanager
from functools import lru_cache

from fastapi import HTTPException, Request

from services.music_manager.api_key import is_system_api_key

logger = logging.getLogger('music-manager.rate-limit')

DEFAULT_ATTEMPTS = 10
DEFAULT_ACCOUNT_ATTEMPTS = 50
DEFAULT_WINDOW_SECONDS = 60
# Loopback and the Docker networks the container sits on, never the LAN (issue #218): a LAN host
# that could name its own client address would get a fresh bucket for every guess.
DEFAULT_TRUSTED_PROXIES = '127.0.0.0/8,::1/128,connected'
# The token in AUTH_TRUSTED_PROXIES that expands to the directly connected IPv4 networks.
CONNECTED = 'connected'
# The kernel's IPv4 routing table of this network namespace (the container's own, in Docker).
ROUTE_TABLE = '/proc/net/route'
_RTF_UP = 0x1
_RTF_GATEWAY = 0x2


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

account_limiter = SlidingWindowRateLimiter(
    attempts=_int_env('AUTH_RATE_LIMIT_ACCOUNT_ATTEMPTS', DEFAULT_ACCOUNT_ATTEMPTS),
    window_seconds=_int_env('AUTH_RATE_LIMIT_WINDOW_SECONDS', DEFAULT_WINDOW_SECONDS),
)


def reset_limiters() -> None:
    """Forget every bucket in both limiters. Used by the test suites."""
    auth_limiter.reset()
    account_limiter.reset()


def _connected_networks(route_table: str = ROUTE_TABLE) -> tuple[ipaddress.IPv4Network, ...]:
    """The IPv4 networks reached without a gateway, read from the kernel's routing table.

    In the music-manager container these are its Docker networks, the bridge nginx and LMS
    call it over, whatever subnet Docker picked for it. The default route never counts: it
    would trust every address. A table that cannot be read gives nothing, so the default
    falls back to loopback alone rather than to a guess.
    """
    try:
        with open(route_table, encoding='ascii') as table:
            lines = table.read().splitlines()[1:]
    except OSError as exc:
        logger.warning('Cannot read %s (%s); AUTH_TRUSTED_PROXIES "connected" trusts nothing', route_table, exc)
        return ()
    networks = []
    for line in lines:
        fields = line.split()
        if len(fields) < 8:
            continue
        try:
            destination, gateway, flags, mask = (int(fields[i], 16) for i in (1, 2, 3, 7))
        except ValueError:
            continue
        if not flags & _RTF_UP or flags & _RTF_GATEWAY or gateway or not mask:
            continue
        # The table is in host byte order, little-endian on every platform this runs on.
        address = ipaddress.IPv4Address(destination.to_bytes(4, 'little'))
        netmask = ipaddress.IPv4Address(mask.to_bytes(4, 'little'))
        try:
            network = ipaddress.IPv4Network(f'{address}/{netmask}', strict=False)
        except ValueError:
            continue
        if network not in networks:
            networks.append(network)
    return tuple(networks)


@lru_cache(maxsize=8)
def _parse_networks(spec: str) -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """The networks in a comma-separated list; an entry that does not parse is skipped, loudly.

    The entry `connected` expands to `_connected_networks()`, read once per value of the
    setting: a container's networks only change when it is recreated.
    """
    networks: list[ipaddress.IPv4Network | ipaddress.IPv6Network] = []
    for entry in spec.split(','):
        entry = entry.strip()
        if not entry:
            continue
        if entry.lower() == CONNECTED:
            networks.extend(_connected_networks())
            continue
        try:
            networks.append(ipaddress.ip_network(entry, strict=False))
        except ValueError:
            logger.warning('Ignoring invalid AUTH_TRUSTED_PROXIES entry %r', entry)
    return tuple(networks)


def _trusted_networks() -> tuple[ipaddress.IPv4Network | ipaddress.IPv6Network, ...]:
    """The networks whose X-Forwarded-For is believed. Read per call, cached per value."""
    return _parse_networks(os.getenv('AUTH_TRUSTED_PROXIES', DEFAULT_TRUSTED_PROXIES))


def _is_trusted_proxy(address: str) -> bool:
    """Whether `address` is on a trusted network. Anything that is not an IP address is not."""
    try:
        ip = ipaddress.ip_address(address)
    except ValueError:
        return False
    if isinstance(ip, ipaddress.IPv6Address) and ip.ipv4_mapped is not None:
        ip = ip.ipv4_mapped
    return any(ip in network for network in _trusted_networks())


def client_key(request: Request) -> str:
    """Identify the caller: its address, as far as the proxies in front can be believed.

    See the module docstring. The X-Forwarded-For chain is only read when the peer is a
    trusted proxy or the request carries the system key, and then from the right: the
    first hop that is not itself a trusted proxy is the client. When every hop is trusted
    (LMS reporting the address of a proxy on the Docker network that it does not look
    behind), the left-most is the best there is.
    """
    peer = request.client.host if request.client else 'unknown'
    forwarded = request.headers.get('x-forwarded-for')
    if not forwarded:
        return peer
    if not (_is_trusted_proxy(peer) or is_system_api_key(request.headers.get('x-api-key'))):
        return peer
    hops = [hop.strip() for hop in forwarded.split(',') if hop.strip()]
    for hop in reversed(hops):
        if not _is_trusted_proxy(hop):
            return hop
    return hops[0] if hops else peer


@contextmanager
def auth_attempt(request: Request, subject: str = '', count_successes: bool = False):
    """Guard one credential check: 429 up front, count it only if it was rejected.

    `subject` narrows the bucket to what is being guessed -- the account name on
    a login -- and adds the account-wide bucket next to the per-client one (see
    the module docstring). Without it the caller has one bucket per endpoint.

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
    client = client_key(request)
    buckets = [(auth_limiter, f'{request.url.path}|{client}|{subject}')]
    if subject:
        buckets.append((account_limiter, f'{request.url.path}|*|{subject}'))

    retry_after = 0
    for limiter, key in buckets:
        is_blocked, wait = limiter.blocked(key)
        if is_blocked:
            retry_after = max(retry_after, wait)
    if retry_after:
        logger.warning('Rate limit hit on %s by %s', request.url.path, client)
        raise HTTPException(
            status_code=429,
            detail='Too many attempts. Try again later.',
            headers={'Retry-After': str(retry_after)},
        )
    try:
        yield
    except HTTPException as exc:
        if count_successes or exc.status_code in (401, 403):
            for limiter, key in buckets:
                limiter.register_attempt(key)
        raise
    else:
        if count_successes:
            for limiter, key in buckets:
                limiter.register_attempt(key)
