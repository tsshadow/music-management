"""Fetch a URL someone else chose without letting it reach the internal network.

The artist image code downloads URLs it did not pick: a curator pastes one into "set
image from URL", and a provider (Spotify, Last.fm, SoundCloud) hands one back in its API
answer. Either can name a host that resolves to the database, the Docker socket proxy,
LMS, the router or the cloud metadata address.

Checking the name and then handing the URL to `requests` is not enough: `requests`
resolves the name a second time, and a DNS server that answers with a public address to
the check and a private one to the fetch (DNS rebinding) walks straight past it. So this
module resolves each host exactly once, refuses the whole URL if any address it got back
is internal, and then connects to one of those checked addresses itself -- sending the
original name as the `Host` header and as the TLS server name, and verifying the
certificate against that name. Redirects are followed by hand, each hop resolved and
checked the same way, up to a hop limit. The body is streamed and cut off at a size cap
and an overall deadline.

The connection never goes through an HTTP(S) proxy from the environment: a proxy would
do its own resolving, which is exactly the second lookup this module exists to avoid.
See docs/bug-reports/114-artist-image-dns-rebinding.md.
"""

from __future__ import annotations

import ipaddress
import socket
import time
from urllib.parse import urljoin, urlsplit

import certifi
import urllib3
from urllib3.exceptions import ConnectTimeoutError, NewConnectionError

from services.common.user_agent import user_agent as _user_agent

DEFAULT_MAX_BYTES = 10 * 1024 * 1024
DEFAULT_MAX_REDIRECTS = 3
DEFAULT_TIMEOUT_SECONDS = 10.0
CHUNK_BYTES = 64 * 1024
REDIRECT_STATUSES = frozenset({301, 302, 303, 307, 308})


def user_agent() -> str:
    """The User-Agent for this module's requests, built on first use."""
    return _user_agent('MuMa-artist-images', '1.0')


# Spelled out rather than left to `is_global` alone, so the ranges this deployment
# actually lives in -- the Docker bridges (172.16/12), the LAN (192.168/16, 10/8), the
# tailnet (CGNAT 100.64/10) and the metadata address (169.254.169.254) -- are refused
# even on a Python whose `is_global` table differs.
INTERNAL_NETWORKS = tuple(
    ipaddress.ip_network(network)
    for network in (
        '0.0.0.0/8',
        '10.0.0.0/8',
        '100.64.0.0/10',
        '127.0.0.0/8',
        '169.254.0.0/16',
        '172.16.0.0/12',
        '192.0.0.0/24',
        '192.0.2.0/24',
        '192.168.0.0/16',
        '198.18.0.0/15',
        '198.51.100.0/24',
        '203.0.113.0/24',
        '224.0.0.0/4',
        '240.0.0.0/4',
        '::/128',
        '::1/128',
        'fc00::/7',
        'fe80::/10',
        'fec0::/10',
        'ff00::/8',
        '2001:db8::/32',
    )
)
# IPv6 prefixes that carry an IPv4 address in their low 32 bits and can be routed to it
# (NAT64). Their IPv4 part must itself be public.
NAT64_NETWORKS = (ipaddress.ip_network('64:ff9b::/96'), ipaddress.ip_network('64:ff9b:1::/48'))


class UnsafeUrl(ValueError):
    """A URL this module refuses to fetch: wrong scheme, unresolvable, not public, or too many redirects."""


class ResponseTooLarge(ValueError):
    """A response body larger than the caller's byte cap."""


class FetchFailed(RuntimeError):
    """The server answered, but not with a usable body (an HTTP error status)."""

    def __init__(self, status: int, url: str):
        super().__init__(f'HTTP {status} from {url}')
        self.status = status


def _embedded_ipv4(address: ipaddress.IPv6Address) -> list[ipaddress.IPv4Address]:
    """The IPv4 addresses an IPv6 address can be routed to: mapped, 6to4, Teredo, NAT64."""
    embedded = []
    if address.ipv4_mapped is not None:
        embedded.append(address.ipv4_mapped)
    if address.sixtofour is not None:
        embedded.append(address.sixtofour)
    if address.teredo is not None:
        embedded.extend(address.teredo)
    if any(address in network for network in NAT64_NETWORKS):
        embedded.append(ipaddress.IPv4Address(int(address) & 0xFFFFFFFF))
    # IPv4-compatible (::a.b.c.d, deprecated but still parsed by some stacks).
    if int(address) >> 32 == 0 and int(address) > 1:
        embedded.append(ipaddress.IPv4Address(int(address)))
    return embedded


def is_public_address(address: ipaddress.IPv4Address | ipaddress.IPv6Address) -> bool:
    """True when `address`, and any IPv4 address hidden inside it, is globally routable unicast."""
    candidates: list[ipaddress.IPv4Address | ipaddress.IPv6Address] = [address]
    if isinstance(address, ipaddress.IPv6Address):
        candidates.extend(_embedded_ipv4(address))
    for candidate in candidates:
        if any(candidate in network for network in INTERNAL_NETWORKS if network.version == candidate.version):
            return False
        # is_global is already False for loopback, link-local and unspecified; multicast
        # and reserved space can still count as "global", so they are refused separately.
        if not candidate.is_global or candidate.is_multicast or candidate.is_reserved:
            return False
    return True


def resolve_public(host: str, port: int) -> list[str]:
    """Resolve `host` once and return its addresses, refusing it if any one is not public.

    One internal address among public ones is enough to refuse: which of them a client
    ends up using is not something the caller controls.
    """
    try:
        infos = socket.getaddrinfo(host, port, proto=socket.IPPROTO_TCP)
    except (ValueError, OSError, UnicodeError) as e:
        raise UnsafeUrl(f'Cannot resolve {host}') from e
    addresses: list[str] = []
    for info in infos:
        text = str(info[4][0]).split('%', 1)[0]
        try:
            address = ipaddress.ip_address(text)
        except ValueError as e:
            raise UnsafeUrl(f'Cannot resolve {host}') from e
        if not is_public_address(address):
            raise UnsafeUrl('URL points at a non-public address')
        if text not in addresses:
            addresses.append(text)
    if not addresses:
        raise UnsafeUrl(f'Cannot resolve {host}')
    return addresses


def split_url(url: str) -> tuple[str, str, int, str]:
    """Scheme, host, port and request target of an http(s) URL; UnsafeUrl for anything else."""
    parts = urlsplit(url)
    scheme = parts.scheme.lower()
    if scheme not in ('http', 'https') or not parts.hostname:
        raise UnsafeUrl('Only http(s) URLs are supported')
    if parts.username or parts.password:
        raise UnsafeUrl('URLs with credentials are not supported')
    try:
        port = parts.port or (443 if scheme == 'https' else 80)
    except ValueError as e:
        raise UnsafeUrl('Invalid port') from e
    target = parts.path or '/'
    if parts.query:
        target = f'{target}?{parts.query}'
    return scheme, parts.hostname, port, target


def _host_header(scheme: str, host: str, port: int) -> str:
    """The Host header for `host`, bracketing IPv6 literals and omitting the default port."""
    name = f'[{host}]' if ':' in host else host
    default = 443 if scheme == 'https' else 80
    return name if port == default else f'{name}:{port}'


def _pool(scheme: str, host: str, address: str, port: int, timeout: float) -> urllib3.HTTPConnectionPool:
    """A connection pool bound to the checked `address`, speaking to `host` by name.

    For https, `server_hostname` puts the name in the TLS SNI and `assert_hostname`
    checks the certificate against the name rather than against the IP, so pinning the
    address loses none of the certificate verification `requests` would have done.
    """
    timeouts = urllib3.Timeout(connect=timeout, read=timeout)
    if scheme == 'https':
        return urllib3.HTTPSConnectionPool(
            address,
            port,
            timeout=timeouts,
            retries=False,
            maxsize=1,
            cert_reqs='CERT_REQUIRED',
            ca_certs=certifi.where(),
            server_hostname=host,
            assert_hostname=host,
        )
    return urllib3.HTTPConnectionPool(address, port, timeout=timeouts, retries=False, maxsize=1)


def _open(url: str, headers: dict, timeout: float):
    """Send one GET for `url` to a checked address; return (pool, response) with the body unread."""
    scheme, host, port, target = split_url(url)
    addresses = resolve_public(host, port)
    request_headers = {
        'User-Agent': user_agent(),
        'Accept': 'image/*,*/*;q=0.8',
        'Accept-Encoding': 'identity',
        **headers,
        'Host': _host_header(scheme, host, port),
    }
    last_error: Exception | None = None
    for address in addresses:
        pool = _pool(scheme, host, address, port, timeout)
        try:
            response = pool.urlopen(
                'GET',
                target,
                headers=request_headers,
                redirect=False,
                retries=False,
                preload_content=False,
                assert_same_host=False,
            )
            return pool, response
        except (NewConnectionError, ConnectTimeoutError) as e:
            # This address did not answer; the next checked one might.
            pool.close()
            last_error = e
        except Exception:
            pool.close()
            raise
    raise ConnectionError(f'Could not connect to {host}: {last_error}')


def fetch(
    url: str,
    *,
    max_bytes: int = DEFAULT_MAX_BYTES,
    max_redirects: int = DEFAULT_MAX_REDIRECTS,
    timeout: float = DEFAULT_TIMEOUT_SECONDS,
    headers: dict | None = None,
) -> bytes:
    """Return the body at a public http(s) `url`, following at most `max_redirects` redirects.

    Raises UnsafeUrl for a URL (or redirect target) that is not public http(s) or for too
    many redirects, ResponseTooLarge once the body passes `max_bytes`, FetchFailed for an
    HTTP error status, and TimeoutError once the whole exchange -- every hop and the body
    -- has taken longer than `timeout` seconds (plus at most one read timeout).
    """
    deadline = time.monotonic() + timeout
    for _ in range(max_redirects + 1):
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError(f'Fetching {url} took longer than {timeout:g}s')
        pool, response = _open(url, headers or {}, remaining)
        try:
            if response.status in REDIRECT_STATUSES:
                location = response.headers.get('Location', '')
                if not location:
                    raise FetchFailed(response.status, url)
                url = urljoin(url, location)
                continue
            if response.status >= 400:
                raise FetchFailed(response.status, url)
            declared = response.headers.get('Content-Length', '')
            if declared.isdigit() and int(declared) > max_bytes:
                raise ResponseTooLarge(f'Response is larger than {max_bytes} bytes')
            data = bytearray()
            # read1, not stream(): stream() blocks until a whole chunk has arrived, so a
            # server dripping a few bytes at a time would never reach the deadline check.
            while chunk := response.read1(CHUNK_BYTES):
                data.extend(chunk)
                if len(data) > max_bytes:
                    raise ResponseTooLarge(f'Response is larger than {max_bytes} bytes')
                if time.monotonic() > deadline:
                    raise TimeoutError(f'Fetching {url} took longer than {timeout:g}s')
            return bytes(data)
        finally:
            response.release_conn()
            pool.close()
    raise UnsafeUrl('Too many redirects')
