"""The `popular-tracks` loop: keep the top tracks of the artists that matter fresh, matched to the library.

docs/designs/old-hits-feed/technical.md, "Popularity crawl". Once an hour the loop looks for
artists whose top list is missing or older than `popular_tracks_refresh_days` and fetches at
most `popular_tracks_max_artists` of them per source:

- **Which artists.** Only those that matter to somebody's profile: a primary artist of a
  track any listener rated 4 or 5 stars, or of at least `popular_tracks_min_listens` listens.
  Never the whole library -- 300k tracks by tens of thousands of artists, most of them heard
  by nobody. Artists are keyed by their normalized name (`library_artists.normalized_name`),
  not by id: a library rebuild renumbers artists and tracks, and the crawl should survive it.
- **Which sources.** Deezer always (no key needed). Last.fm only when `lastfm_api_key` is set
  on the config page; without one the source is simply skipped.
- **What is stored.** Per artist and source, the list as the source reported it in
  `artist_popular_tracks`, each row with the library track it matched (`matched_track_uid`,
  stable across rebuilds, and `matched_work_id` as found at the time), and one row in
  `artist_popularity_fetches` saying when, and whether the artist was found. A failed fetch is
  retried after a day; a throttled source ends the round for that source, and the next round
  resumes with the artists still due -- nothing is lost, the work is simply spread out.

Only artist names are sent out. The feed (`feeds/old_hits_build.py`) reads the stored matches
and never calls out itself.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from services.common.config_store import ConfigStore
from services.music_manager.database import get_db_connection, transaction
from services.music_manager.popular_tracks.clients import (
    DEEZER,
    LASTFM,
    ArtistTopTracks,
    DeezerClient,
    LastFmClient,
    SourceFailed,
    SourceThrottled,
)
from services.music_manager.popular_tracks.matcher import ArtistIndex, LibraryTrack
from services.music_manager.scrobble_matching import normalize
from services.music_manager.thread_registry import default_stale_after, run_forever

logger = logging.getLogger('music-manager.popular-tracks')

#: The name under which the loop appears in `/health` `threads`.
THREAD_NAME = 'popular-tracks'
CHECK_EVERY_SECONDS = 3600
STALE_AFTER_SECONDS = default_stale_after(CHECK_EVERY_SECONDS)
#: A failed fetch (network error, unexpected answer) is retried after this long, not a week.
RETRY_FAILED_AFTER = timedelta(days=1)

DEFAULT_REFRESH_DAYS = 7
DEFAULT_MAX_ARTISTS = 150
DEFAULT_MIN_LISTENS = 5
DEFAULT_MAX_MINUTES = 30

stop_event = threading.Event()


def _positive_int(value: Any, default: int) -> int:
    """`value` as a positive integer, or `default` when missing, unparsable or not positive."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    return number if number > 0 else default


def _enabled(value: Any) -> bool:
    """The switch as a bool; environment strings read the way a boolean setting would."""
    if value is None:
        return True
    if isinstance(value, str):
        return value.strip().lower() not in ('0', 'false', 'no', 'off', '')
    return bool(value)


def settings_snapshot(settings: Any = None) -> dict[str, Any]:
    """The loop's settings, validated, as this round will use them."""
    settings = settings if settings is not None else ConfigStore()
    return {
        'enabled': _enabled(settings.get('popular_tracks_enabled')),
        'refresh_days': _positive_int(settings.get('popular_tracks_refresh_days'), DEFAULT_REFRESH_DAYS),
        'max_artists': _positive_int(settings.get('popular_tracks_max_artists'), DEFAULT_MAX_ARTISTS),
        'min_listens': _positive_int(settings.get('popular_tracks_min_listens'), DEFAULT_MIN_LISTENS),
        'max_minutes': DEFAULT_MAX_MINUTES,
        'lastfm_api_key': (settings.get('lastfm_api_key') or '').strip(),
    }


# ----------------------------------------------------------------------------- SQL

#: The artists that matter, by normalized name, with one display spelling each. Two `%s`: the
#: minimum listen count, then the source; then the two cutoffs and the limit.
DUE_ARTISTS_SQL = """
    SELECT x.artist_key, x.name
    FROM (
        SELECT a.normalized_name AS artist_key, MIN(a.name) AS name
        FROM library_artists a
        WHERE a.normalized_name IS NOT NULL AND a.normalized_name <> ''
          AND (
            a.id IN (
                SELECT t.primary_artist_id FROM rating_tracks r
                JOIN library_tracks t ON t.track_uid = r.entity_id
                WHERE r.entity_type = 'track' AND r.rating >= 4
            )
            OR a.id IN (
                SELECT t.primary_artist_id FROM scrobble_listens s
                JOIN library_tracks t ON t.id = s.track_id
                GROUP BY t.primary_artist_id
                HAVING COUNT(*) >= %s
            )
          )
        GROUP BY a.normalized_name
    ) x
    LEFT JOIN artist_popularity_fetches f ON f.artist_key = x.artist_key AND f.source = %s
    WHERE f.fetched_at IS NULL
       OR f.fetched_at < %s
       OR (f.status = 'error' AND f.fetched_at < %s)
    ORDER BY f.fetched_at IS NOT NULL, f.fetched_at, x.artist_key
    LIMIT %s
"""

#: Every library track credited to an artist (primary, or featured), with its work's canonical.
ARTIST_TRACKS_SQL = """
    SELECT t.id, t.track_uid, t.title, t.work_id, w.canonical_track_id
    FROM library_tracks t
    JOIN library_artists a ON a.id = t.primary_artist_id
    LEFT JOIN library_works w ON w.id = t.work_id
    WHERE a.normalized_name = %s AND t.track_uid IS NOT NULL
    UNION
    SELECT t.id, t.track_uid, t.title, t.work_id, w.canonical_track_id
    FROM library_track_artists ta
    JOIN library_artists a ON a.id = ta.artist_id
    JOIN library_tracks t ON t.id = ta.track_id
    LEFT JOIN library_works w ON w.id = t.work_id
    WHERE a.normalized_name = %s AND ta.role IN ('primary', 'featuring') AND t.track_uid IS NOT NULL
"""

DELETE_TRACKS_SQL = 'DELETE FROM artist_popular_tracks WHERE artist_key = %s AND source = %s'

INSERT_TRACK_SQL = """
    INSERT IGNORE INTO artist_popular_tracks
        (artist_key, source, external_track_id, title, normalized_title, popularity, position,
         matched_track_uid, matched_work_id, fetched_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
"""

UPSERT_FETCH_SQL = """
    INSERT INTO artist_popularity_fetches
        (artist_key, source, artist_name, external_artist_id, status, track_count, matched_count, fetched_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE
        artist_name = VALUES(artist_name),
        external_artist_id = VALUES(external_artist_id),
        status = VALUES(status),
        track_count = VALUES(track_count),
        matched_count = VALUES(matched_count),
        fetched_at = VALUES(fetched_at)
"""

#: A failed fetch: status and time only, so the counts and the stored list of the last good
#: fetch stay as they were until a retry succeeds.
RECORD_FAILURE_SQL = """
    INSERT INTO artist_popularity_fetches (artist_key, source, artist_name, status, fetched_at)
    VALUES (%s, %s, %s, 'error', %s)
    ON DUPLICATE KEY UPDATE status = VALUES(status), fetched_at = VALUES(fetched_at)
"""


class PopularTracksStore:
    """Every statement the loop runs, on one connection per call."""

    def __init__(self, connect: Callable[[], Any] = get_db_connection):
        self._connect_fn = connect

    def _connect(self) -> Any:
        conn = self._connect_fn()
        if not conn:
            raise RuntimeError('database connection failed')
        return conn

    def due_artists(self, source: str, config: dict, now: datetime) -> list[tuple[str, str]]:
        """`(artist_key, name)` of the artists whose `source` list is missing or stale, oldest first."""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    DUE_ARTISTS_SQL,
                    (
                        config['min_listens'],
                        source,
                        now - timedelta(days=config['refresh_days']),
                        now - RETRY_FAILED_AFTER,
                        config['max_artists'],
                    ),
                )
                return [(row['artist_key'], row['name']) for row in cursor.fetchall()]
        finally:
            conn.close()

    def artist_tracks(self, artist_key: str) -> list[LibraryTrack]:
        """The library tracks credited to the artist, for the matcher."""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(ARTIST_TRACKS_SQL, (artist_key, artist_key))
                return [
                    LibraryTrack(
                        id=row['id'],
                        track_uid=row['track_uid'],
                        title=row.get('title'),
                        work_id=row.get('work_id'),
                        canonical_track_id=row.get('canonical_track_id'),
                    )
                    for row in cursor.fetchall()
                ]
        finally:
            conn.close()

    def save(
        self, artist_key: str, name: str, result: ArtistTopTracks, index: ArtistIndex, now: datetime
    ) -> tuple[int, int]:
        """Replace the artist's list for `result.source`, matched; returns `(tracks, matched)`."""
        rows = []
        matched = 0
        for track in result.tracks:
            match = index.match(track.title)
            if match is not None:
                matched += 1
            rows.append(
                (
                    artist_key,
                    result.source,
                    track.external_id[:64],
                    track.title[:512],
                    normalize(track.title)[:191],
                    track.popularity,
                    track.position,
                    match.track.track_uid if match else None,
                    match.track.work_id if match else None,
                    now,
                )
            )
        status = 'ok' if result.external_artist_id is not None else 'not_found'
        conn = self._connect()
        try:
            with transaction(conn), conn.cursor() as cursor:
                cursor.execute(DELETE_TRACKS_SQL, (artist_key, result.source))
                if rows:
                    cursor.executemany(INSERT_TRACK_SQL, rows)
                cursor.execute(
                    UPSERT_FETCH_SQL,
                    (artist_key, result.source, name[:255], result.external_artist_id, status, len(rows), matched, now),
                )
        finally:
            conn.close()
        return len(rows), matched

    def record_failure(self, artist_key: str, name: str, source: str, now: datetime) -> None:
        """Mark a fetch as failed; the previous list, if any, is kept and retried after a day."""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(RECORD_FAILURE_SQL, (artist_key, source, name[:255], now))
            conn.commit()
        finally:
            conn.close()


@dataclass
class RoundResult:
    """What one round did, per source, for the summary line."""

    fetched: dict[str, int] = field(default_factory=dict)
    not_found: dict[str, int] = field(default_factory=dict)
    failed: dict[str, int] = field(default_factory=dict)
    matched: dict[str, int] = field(default_factory=dict)
    throttled: list[str] = field(default_factory=list)
    requests: int = 0
    stopped_early: bool = False


def build_clients(config: dict) -> dict[str, Any]:
    """The clients this round uses: Deezer always, Last.fm only with a key."""
    clients: dict[str, Any] = {DEEZER: DeezerClient()}
    if config.get('lastfm_api_key'):
        clients[LASTFM] = LastFmClient(config['lastfm_api_key'])
    return clients


def run_round(
    config: dict,
    store: PopularTracksStore,
    clients: dict[str, Any],
    now: Callable[[], datetime] = datetime.now,
    clock: Callable[[], float] = time.monotonic,
) -> RoundResult:
    """Fetch and match every due artist, source by source, until done, throttled or out of time."""
    result = RoundResult()
    deadline = clock() + 60 * config['max_minutes']
    indexes: dict[str, ArtistIndex] = {}
    for source, client in clients.items():
        for counter in (result.fetched, result.not_found, result.failed, result.matched):
            counter[source] = 0
        for artist_key, name in store.due_artists(source, config, now()):
            if clock() > deadline or stop_event.is_set():
                result.stopped_early = True
                break
            try:
                fetched = client.fetch(name)
            except SourceThrottled as exc:
                logger.warning('%s: %s; resuming next round', THREAD_NAME, exc)
                result.throttled.append(source)
                break
            except SourceFailed as exc:
                logger.debug('%s: %s failed for %r: %s', THREAD_NAME, source, name, exc)
                store.record_failure(artist_key, name, source, now())
                result.failed[source] += 1
                continue
            if artist_key not in indexes:
                indexes[artist_key] = ArtistIndex(store.artist_tracks(artist_key))
            _, matched = store.save(artist_key, name, fetched, indexes[artist_key], now())
            if fetched.external_artist_id is None:
                result.not_found[source] += 1
            else:
                result.fetched[source] += 1
                result.matched[source] += matched
        result.requests += getattr(client, 'requests', 0)
    return result


def _log_summary(result: RoundResult) -> None:
    """One INFO line when the round did anything, nothing when every list was fresh."""
    touched = sum(result.fetched.values()) + sum(result.not_found.values()) + sum(result.failed.values())
    if not touched and not result.throttled:
        logger.debug('%s: every top list is fresh', THREAD_NAME)
        return
    logger.info(
        '%s: fetched %s, not found %s, failed %s, matched %s tracks, %d requests%s%s',
        THREAD_NAME,
        result.fetched,
        result.not_found,
        result.failed,
        result.matched,
        result.requests,
        f', throttled by {result.throttled}' if result.throttled else '',
        ', stopped early' if result.stopped_early else '',
    )


def popular_tracks_tick(
    settings: Any = None,
    *,
    store: PopularTracksStore | None = None,
    clients_factory: Callable[[dict], dict[str, Any]] = build_clients,
) -> float:
    """One check: a round when switched on. A database failure raises so `run_forever` backs off."""
    config = settings_snapshot(settings)
    if not config['enabled']:
        logger.debug('%s: switched off on the config page', THREAD_NAME)
        return CHECK_EVERY_SECONDS
    result = run_round(config, store or PopularTracksStore(), clients_factory(config))
    _log_summary(result)
    return CHECK_EVERY_SECONDS


def run_popular_tracks(stop: threading.Event | None = None) -> None:
    """The `popular-tracks` thread: a round on start, then hourly."""
    run_forever(
        THREAD_NAME,
        popular_tracks_tick,
        CHECK_EVERY_SECONDS,
        stale_after=STALE_AFTER_SECONDS,
        stop=stop or stop_event,
    )
