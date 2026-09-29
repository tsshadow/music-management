"""Deezer and Last.fm top-track clients for the popular-tracks worker.

Only an artist name ever leaves the process -- never a title from the library, never a
listen. Both clients are polite by construction: every request goes through a
`RateLimiter` (at most four a second, under Deezer's documented 50 per 5 s and Last.fm's
five a second), a refusal for load (HTTP 429, Deezer's quota error code 4, Last.fm's error
29) is retried with a doubling backoff, and a refusal that outlasts the backoff raises
`SourceThrottled` so the worker ends its round and resumes the next one where it stopped.

The HTTP call itself is injected (`http_get`), so the tests replay recorded responses and
never touch the network.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

from services.music_manager.scrobble_matching import normalize

logger = logging.getLogger('music-manager.popular-tracks')

DEEZER = 'deezer'
LASTFM = 'lastfm'

DEEZER_API = 'https://api.deezer.com'
LASTFM_API = 'https://ws.audioscrobbler.com/2.0/'

#: Seconds between two requests to one source: four a second.
MIN_INTERVAL_SECONDS = 0.25
#: How many times a throttled request is retried before the round gives up on the source.
MAX_RETRIES = 3
#: The first backoff after a throttled request; doubles per retry.
FIRST_BACKOFF_SECONDS = 5.0
TIMEOUT_SECONDS = 20
USER_AGENT = 'muma-popular-tracks/0.1 (https://gitlab.com/muma/music-management)'
#: How many top tracks are asked for per artist.
TOP_LIMIT = 50

#: Deezer answers a quota breach with HTTP 200 and this error code.
DEEZER_QUOTA_CODE = 4
#: Deezer's "no data" error, returned for an unknown artist id.
DEEZER_NO_DATA_CODE = 800
#: Last.fm's "rate limit exceeded" and "invalid parameters / artist not found" codes.
LASTFM_RATE_LIMIT_CODE = 29
LASTFM_NOT_FOUND_CODE = 6


class SourceThrottled(Exception):
    """A source kept refusing for load after every retry; stop asking it this round."""


class SourceFailed(Exception):
    """A source answered with something unusable (network error, bad JSON, unexpected error)."""


@dataclass(frozen=True)
class TopTrack:
    """One entry of an artist's top list, as the source reports it."""

    external_id: str
    title: str
    position: int
    popularity: int | None


@dataclass(frozen=True)
class ArtistTopTracks:
    """What one source knows about one artist: its id there (None when not found) and its top tracks."""

    source: str
    external_artist_id: str | None
    tracks: list[TopTrack]


class RateLimiter:
    """Spaces calls at least `interval` seconds apart. `clock`/`sleep` are injectable for tests."""

    def __init__(
        self,
        interval: float = MIN_INTERVAL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self._last: float | None = None

    def wait(self) -> None:
        """Block until the next call is allowed, then claim the slot."""
        now = self.clock()
        if self._last is not None:
            remaining = self.interval - (now - self._last)
            if remaining > 0:
                self.sleep(remaining)
                now = self.clock()
        self._last = now


def default_http_get(url: str, params: dict | None = None) -> tuple[int, Any]:
    """`GET url` and return `(status, parsed JSON or None)`. Network errors raise `SourceFailed`."""
    try:
        response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS, headers={'User-Agent': USER_AGENT})
    except requests.RequestException as exc:
        raise SourceFailed(str(exc)) from exc
    try:
        body = response.json()
    except ValueError:
        body = None
    return response.status_code, body


HttpGet = Callable[..., tuple[int, Any]]


class _Client:
    """The shared request loop: rate limit, retry on throttling, raise on anything else unusable."""

    source = ''

    def __init__(self, http_get: HttpGet | None = None, limiter: RateLimiter | None = None, sleep=time.sleep):
        self.http_get = http_get or default_http_get
        self.limiter = limiter or RateLimiter()
        self.sleep = sleep
        #: Requests made (retries included), for the round's summary line.
        self.requests = 0

    def _throttled(self, status: int, body: Any) -> bool:
        raise NotImplementedError

    def _get(self, url: str, params: dict | None = None) -> Any:
        backoff = FIRST_BACKOFF_SECONDS
        for attempt in range(MAX_RETRIES + 1):
            self.limiter.wait()
            self.requests += 1
            status, body = self.http_get(url, params=params)
            if not self._throttled(status, body):
                if status >= 400 or body is None:
                    raise SourceFailed(f'{self.source}: HTTP {status}')
                return body
            if attempt == MAX_RETRIES:
                break
            logger.debug('%s throttled us, backing off %.0fs', self.source, backoff)
            self.sleep(backoff)
            backoff *= 2
        raise SourceThrottled(f'{self.source} kept refusing for load after {MAX_RETRIES} retries')


def _error_code(body: Any) -> int | None:
    """Deezer's `{"error": {"code": n}}` or Last.fm's `{"error": n}` code, else None."""
    if not isinstance(body, dict) or 'error' not in body:
        return None
    error = body['error']
    if isinstance(error, dict):
        error = error.get('code')
    try:
        return int(error)
    except (TypeError, ValueError):
        return -1


class DeezerClient(_Client):
    """Deezer's public API: `search/artist` for the id, `artist/<id>/top` for the list. No key."""

    source = DEEZER

    def _throttled(self, status: int, body: Any) -> bool:
        return status == 429 or _error_code(body) == DEEZER_QUOTA_CODE

    def find_artist(self, name: str) -> str | None:
        """The Deezer id of the first result whose name folds to the same key as `name`, or None.

        The first *exact* match, not the first result: a search for a small act returns a
        famous namesake or a collaboration ("Wildstylez, Headhunterz and ...") first.
        """
        key = normalize(name)
        body = self._get(f'{DEEZER_API}/search/artist', {'q': name, 'limit': 5})
        if _error_code(body) is not None:
            raise SourceFailed(f'deezer: search error {_error_code(body)}')
        for artist in body.get('data') or []:
            if normalize(artist.get('name')) == key and artist.get('id') is not None:
                return str(artist['id'])
        return None

    def top_tracks(self, artist_id: str) -> list[TopTrack]:
        """The artist's top tracks, most popular first, with Deezer's `rank` as popularity.

        `title_short` is preferred over `title`: it is the title without Deezer's version
        suffix ("Disrespect" rather than "Disrespect (Original Mix)"), which is what a library
        title is matched against.
        """
        body = self._get(f'{DEEZER_API}/artist/{artist_id}/top', {'limit': TOP_LIMIT})
        code = _error_code(body)
        if code == DEEZER_NO_DATA_CODE:
            return []
        if code is not None:
            raise SourceFailed(f'deezer: top error {code}')
        tracks = []
        for index, track in enumerate(body.get('data') or []):
            title = (track.get('title_short') or track.get('title') or '').strip()
            if not title or track.get('id') is None:
                continue
            tracks.append(TopTrack(str(track['id']), title, index + 1, _int_or_none(track.get('rank'))))
        return tracks

    def fetch(self, name: str) -> ArtistTopTracks:
        """Both steps for one artist name."""
        artist_id = self.find_artist(name)
        if artist_id is None:
            return ArtistTopTracks(DEEZER, None, [])
        return ArtistTopTracks(DEEZER, artist_id, self.top_tracks(artist_id))


class LastFmClient(_Client):
    """Last.fm's `artist.getTopTracks`, one request per artist. Needs `lastfm_api_key`."""

    source = LASTFM

    def __init__(self, api_key: str, **kwargs):
        super().__init__(**kwargs)
        self.api_key = api_key

    def _throttled(self, status: int, body: Any) -> bool:
        return status == 429 or _error_code(body) == LASTFM_RATE_LIMIT_CODE

    def fetch(self, name: str) -> ArtistTopTracks:
        """The artist's top tracks by listener count, Last.fm's own order kept as the position.

        An unknown artist is Last.fm error 6, which Last.fm sends with HTTP 400; that is an
        answer ("not found"), not a failure, so it is handled before the generic status check.
        """
        params = {
            'method': 'artist.gettoptracks',
            'artist': name,
            'autocorrect': 1,
            'limit': TOP_LIMIT,
            'api_key': self.api_key,
            'format': 'json',
        }
        body = self._get(LASTFM_API, params)
        code = _error_code(body)
        if code == LASTFM_NOT_FOUND_CODE:
            return ArtistTopTracks(LASTFM, None, [])
        if code is not None:
            raise SourceFailed(f'lastfm: error {code}')
        entries = (body.get('toptracks') or {}).get('track') or []
        if isinstance(entries, dict):
            entries = [entries]
        tracks = []
        for index, entry in enumerate(entries):
            title = (entry.get('name') or '').strip()
            if not title:
                continue
            position = _int_or_none((entry.get('@attr') or {}).get('rank')) or index + 1
            external_id = entry.get('mbid') or f'{normalize(name)}|{normalize(title)}'
            tracks.append(TopTrack(external_id[:64], title, position, _int_or_none(entry.get('listeners'))))
        return ArtistTopTracks(LASTFM, normalize(name)[:64] if tracks else None, tracks)

    def _get(self, url: str, params: dict | None = None) -> Any:
        """Last.fm reports "not found" with HTTP 400 and an error body; pass that body through."""
        backoff = FIRST_BACKOFF_SECONDS
        for attempt in range(MAX_RETRIES + 1):
            self.limiter.wait()
            self.requests += 1
            status, body = self.http_get(url, params=params)
            if self._throttled(status, body):
                if attempt == MAX_RETRIES:
                    break
                self.sleep(backoff)
                backoff *= 2
                continue
            if _error_code(body) is not None:
                return body
            if status >= 400 or body is None:
                raise SourceFailed(f'lastfm: HTTP {status}')
            return body
        raise SourceThrottled(f'lastfm kept refusing for load after {MAX_RETRIES} retries')


def _int_or_none(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
