"""Album facts from a store, asked once and kept: release date, label, UPC.

A scene release's .nfo links the album at a store far more often than it states a release date:
4.514 of the 6.546 .nfo files in the import queue on 2026-10-02 link Deezer. Deezer's public API
answers `GET https://api.deezer.com/album/<id>` without a key with `release_date`, `label` and
`upc` -- for Minus Militia's `Recover The Archive` 2026-10-02, `b2s Records`, 8719244873593.

Only Deezer is asked. Beatport (1.499 links), Qobuz and Tidal have no public album API.

Three rules shape this module:

* **Polite.** Every request waits for a process-wide slot four a second, under Deezer's documented
  50 per 5 s, the same pace as the popular-tracks client. Deezer answers a quota breach with HTTP
  200 and error code 4 (or HTTP 429): that raises `StoreThrottled` and the caller stops asking for
  the rest of its cycle rather than retrying in a loop.
* **Kept.** A found album and a gone album are stored in `release_store_lookups`, so a release is
  asked about once, whichever process asks -- the importer fills the table, the tagger in
  music-manager only reads it (no `Budget`, so no request). A gone album is asked again after
  `NOT_FOUND_RETRY_DAYS`; a transient failure is not stored at all.
* **Optional.** Every failure -- no network, a timeout, a database that cannot be reached -- comes
  back as None, and the caller carries on as if the .nfo had no link.
"""

from __future__ import annotations

import logging
import re
import threading
import time
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from typing import Any

from services.common.release_nfo import StoreLink
from services.common.user_agent import user_agent as _user_agent

logger = logging.getLogger('importer.store-lookup')

DEEZER = 'deezer'
DEEZER_ALBUM_URL = 'https://api.deezer.com/album/{album_id}'
#: Deezer answers a quota breach with HTTP 200 and this error code; 800 is "no data".
DEEZER_QUOTA_CODE = 4
DEEZER_NO_DATA_CODE = 800

#: Seconds between two requests from this process: four a second.
MIN_INTERVAL_SECONDS = 0.25
TIMEOUT_SECONDS = 15


def user_agent() -> str:
    """The User-Agent for this module's requests, built on first use."""
    return _user_agent('muma-importer', '0.1')


#: How long a gone album stays gone before it is asked about again.
NOT_FOUND_RETRY_DAYS = 30
#: Albums kept in memory per process, so a tagging round does not query the table per track.
MEMORY_SIZE = 4096

OK = 'ok'
NOT_FOUND = 'not_found'

SELECT_SQL = (
    'SELECT status, label, upc, release_date, title, fetched_at FROM release_store_lookups '
    'WHERE store = %s AND album_id = %s'
)
UPSERT_SQL = (
    'INSERT INTO release_store_lookups (store, album_id, status, label, upc, release_date, title, fetched_at) '
    'VALUES (%s, %s, %s, %s, %s, %s, %s, %s) '
    'ON DUPLICATE KEY UPDATE status = VALUES(status), label = VALUES(label), upc = VALUES(upc), '
    'release_date = VALUES(release_date), title = VALUES(title), fetched_at = VALUES(fetched_at)'
)

_FULL_DATE = re.compile(r'\d{4}-\d{2}-\d{2}')


class StoreThrottled(Exception):
    """The store refused for load; stop asking it for the rest of this cycle."""


@dataclass(frozen=True)
class StoreAlbum:
    """What a store says about one album. `status` is `ok` or `not_found`."""

    store: str
    album_id: str
    status: str
    label: str | None = None
    upc: str | None = None
    release_date: str | None = None
    title: str | None = None
    fetched_at: datetime | None = None

    @property
    def found(self) -> bool:
        """Whether the store knows the album."""
        return self.status == OK

    @property
    def full_date(self) -> str | None:
        """The release date when it is a whole `YYYY-MM-DD` and not Deezer's `0000-00-00`."""
        value = self.release_date or ''
        if not _FULL_DATE.fullmatch(value) or value.startswith('0000') or '-00' in value:
            return None
        return value


class _Pace:
    """One request slot per `interval` seconds for the whole process."""

    def __init__(self, interval: float, clock: Callable[[], float] = time.monotonic, sleep=time.sleep):
        self.interval = interval
        self.clock = clock
        self.sleep = sleep
        self._last: float | None = None
        self._lock = threading.Lock()

    def wait(self) -> None:
        """Block until the next request may go out, then claim it."""
        with self._lock:
            now = self.clock()
            if self._last is not None and now - self._last < self.interval:
                self.sleep(self.interval - (now - self._last))
                now = self.clock()
            self._last = now


_PACE = _Pace(MIN_INTERVAL_SECONDS)


def _default_http_get(url: str) -> tuple[int, Any]:
    """`GET url` -> (status, parsed JSON or None). Raises OSError-like errors on network trouble."""
    import requests

    response = requests.get(url, timeout=TIMEOUT_SECONDS, headers={'User-Agent': user_agent()})
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


def _error_code(body: Any) -> int | None:
    if not isinstance(body, dict) or not isinstance(body.get('error'), dict):
        return None
    try:
        return int(body['error'].get('code'))
    except (TypeError, ValueError):
        return -1


def fetch_deezer(album_id: str, http_get=None, pace: _Pace | None = None, now=None) -> StoreAlbum | None:
    """Ask Deezer about one album. None on a transient failure; raises StoreThrottled on a quota refusal."""
    (pace or _PACE).wait()
    try:
        status, body = (http_get or _default_http_get)(DEEZER_ALBUM_URL.format(album_id=album_id))
    except Exception as exc:  # noqa: BLE001 - the network is optional
        logger.info('Deezer album %s not reachable: %s', album_id, exc)
        return None
    code = _error_code(body)
    if status == 429 or code == DEEZER_QUOTA_CODE:
        raise StoreThrottled(f'deezer refused album {album_id} for load')
    fetched = now or datetime.now(UTC)
    if status == 404 or code == DEEZER_NO_DATA_CODE:
        return StoreAlbum(DEEZER, str(album_id), NOT_FOUND, fetched_at=fetched)
    if status >= 400 or not isinstance(body, dict) or code is not None:
        logger.info('Deezer album %s answered HTTP %s, error %s', album_id, status, code)
        return None

    def text(key: str, limit: int) -> str | None:
        value = body.get(key)
        if value is None:
            return None
        return str(value).strip()[:limit] or None

    return StoreAlbum(
        DEEZER,
        str(album_id),
        OK,
        label=text('label', 255),
        upc=text('upc', 32),
        release_date=text('release_date', 10),
        title=text('title', 255),
        fetched_at=fetched,
    )


class Budget:
    """How many network lookups a caller may still make; None is unlimited."""

    def __init__(self, remaining: int | None = None):
        self.remaining = remaining
        self.throttled = False

    def allows(self) -> bool:
        """Whether one more request may go out."""
        return not self.throttled and (self.remaining is None or self.remaining > 0)

    def spend(self) -> None:
        """Count one request."""
        if self.remaining is not None:
            self.remaining -= 1


class StoreCache:
    """`release_store_lookups` in front of the store, plus a small in-memory layer.

    `connection_factory` returns a context manager yielding a DB-API connection (DatabaseConnector's
    `connection`); it is injectable, like `http_get`, so the tests need neither a database nor the
    network.
    """

    def __init__(self, connection_factory=None, http_get=None, pace: _Pace | None = None, clock=None):
        self._connection_factory = connection_factory
        self._http_get = http_get
        self._pace = pace
        self._clock = clock or (lambda: datetime.now(UTC))
        self._memory: OrderedDict[tuple[str, str], StoreAlbum | None] = OrderedDict()

    def _connection(self):
        if self._connection_factory is None:
            from services.common.Helpers.DatabaseConnector import DatabaseConnector

            self._connection_factory = DatabaseConnector().connection
        return self._connection_factory()

    def _remember(self, key: tuple[str, str], album: StoreAlbum | None) -> None:
        self._memory[key] = album
        self._memory.move_to_end(key)
        while len(self._memory) > MEMORY_SIZE:
            self._memory.popitem(last=False)

    def cached(self, store: str, album_id: str) -> StoreAlbum | None:
        """The stored answer for an album, or None when there is none (or the table is unreachable)."""
        key = (store, str(album_id))
        if key in self._memory:
            return self._memory[key]
        try:
            with self._connection() as connection, connection.cursor() as cursor:
                cursor.execute(SELECT_SQL, key)
                row = cursor.fetchone()
        except Exception as exc:  # noqa: BLE001 - a cache that cannot be read is an empty cache
            logger.debug('release_store_lookups not readable: %s', exc)
            return None
        album = None
        if row:
            status, label, upc, release_date, title, fetched_at = row
            album = StoreAlbum(store, str(album_id), str(status), label, upc, release_date, title, fetched_at)
        self._remember(key, album)
        return album

    def _store(self, album: StoreAlbum) -> None:
        try:
            with self._connection() as connection:
                with connection.cursor() as cursor:
                    cursor.execute(
                        UPSERT_SQL,
                        (
                            album.store,
                            album.album_id,
                            album.status,
                            album.label,
                            album.upc,
                            album.release_date,
                            album.title,
                            (album.fetched_at or self._clock()).replace(tzinfo=None),
                        ),
                    )
                connection.commit()
        except Exception as exc:  # noqa: BLE001 - the answer is still used this time
            logger.warning('Could not store the %s answer for album %s: %s', album.store, album.album_id, exc)

    def is_stale(self, album: StoreAlbum) -> bool:
        """Whether a stored `not_found` is old enough to ask about again."""
        if album.found or album.fetched_at is None:
            return False
        fetched = album.fetched_at if album.fetched_at.tzinfo else album.fetched_at.replace(tzinfo=UTC)
        return self._clock() - fetched > timedelta(days=NOT_FOUND_RETRY_DAYS)

    def lookup(self, link: StoreLink | None, budget: Budget | None = None) -> StoreAlbum | None:
        """The album behind `link`: from the table, else from the store when `budget` allows.

        Without a budget nothing goes over the network -- the tagger's mode. Returns None for a
        store this module does not ask, an album nobody has fetched yet, or any failure.
        """
        if link is None or link.store != DEEZER:
            return None
        album = self.cached(link.store, link.album_id)
        if album is not None and not self.is_stale(album):
            return album
        if budget is None or not budget.allows():
            return album
        budget.spend()
        try:
            fetched = fetch_deezer(link.album_id, http_get=self._http_get, pace=self._pace, now=self._clock())
        except StoreThrottled as exc:
            logger.warning('%s; no more store lookups this cycle', exc)
            budget.throttled = True
            return album
        if fetched is None:
            return album
        self._store(fetched)
        self._remember((link.store, link.album_id), fetched)
        return fetched
