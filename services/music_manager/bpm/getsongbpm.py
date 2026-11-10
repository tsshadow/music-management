"""The tempo GetSongBPM lists for a song, asked once per artist and title and kept (issue #152).

docs/designs/getsongbpm-prior/technical.md. A mainstream track (Hitzone, Spotify, Lidarr, Top 100)
without a label or artist prior has only the general priors to choose its octave on, so such a
fold is never "reliable". GetSongBPM (https://getsongbpm.com, free API key, attribution link
required) lists a tempo for most mainstream songs. Its value becomes one more evidence term in the
octave choice (`octave.EVIDENCE_EXTERNAL`), never the measurement itself.

Three rules shape this module, the same as the importer's Deezer lookup (`services/common/store_lookup.py`):

* **Off without a key.** With `getsongbpm_api_key` empty nothing is asked and nothing cached is used.
* **Polite.** One request per `MIN_INTERVAL_SECONDS` for the whole process, at most `PASS_BUDGET`
  per pass, a pass every `PASS_SECONDS`. HTTP 429 or a refused key stops the pass.
* **Kept.** A found song and a song GetSongBPM does not know are stored in `getsongbpm_lookups`
  under a hash of the normalised artist and title, so a song is asked about once. A miss is asked
  again after `NOT_FOUND_RETRY_DAYS`; a transient failure is not stored at all.

The API key travels in the query string, so no URL and no exception text from the HTTP client is
ever logged.
"""

from __future__ import annotations

import hashlib
import logging
import re
import threading
import time
import unicodedata
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any

from services.common.user_agent import user_agent as _user_agent
from services.music_manager.bpm import octave

logger = logging.getLogger('music-manager.bpm')

SOURCE = octave.EVIDENCE_EXTERNAL
API_URL = 'https://api.getsongbpm.com/search/'
#: The attribution link GetSongBPM asks every user of its API to show.
ATTRIBUTION_URL = 'https://getsongbpm.com'

MIN_INTERVAL_SECONDS = 1.0
TIMEOUT_SECONDS = 15
#: How often the analyzer runs a lookup pass, and how many songs one pass may ask about.
PASS_SECONDS = 600.0
PASS_BUDGET = 50
#: How long the analyzer waits after GetSongBPM refused the key, unless the key changes.
KEY_REJECTED_WAIT_SECONDS = 86400.0
#: How long a song GetSongBPM did not know stays unknown before it is asked about again.
NOT_FOUND_RETRY_DAYS = 90
#: A listed tempo outside this range is noise, not a tempo.
VALID_MIN = 40.0
VALID_MAX = 250.0

OK = 'ok'
NOT_FOUND = 'not_found'


def user_agent() -> str:
    """The User-Agent for this module's requests, built on first use."""
    return _user_agent('muma-bpm-analyzer', '0.1')


# ----------------------------------------------------------------------------- normalising

_BRACKETS = re.compile(r'[(\[{][^)\]}]*[)\]}]')
_FEAT = re.compile(r'\s(?:feat\.?|ft\.?|featuring)\s.*$', re.IGNORECASE)
_ARTIST_SPLIT = re.compile(r'\s*(?:,|&|\bx\b|\bvs\.?|\band\b|/|;)\s*', re.IGNORECASE)
_NOT_WORD = re.compile(r'[^0-9a-z]+')


def _fold(text: str) -> str:
    """Lower-case ASCII letters and digits only, accents dropped, words single-spaced."""
    decomposed = unicodedata.normalize('NFKD', text)
    plain = ''.join(ch for ch in decomposed if not unicodedata.combining(ch)).lower()
    return _NOT_WORD.sub(' ', plain).strip()


def clean_title(title: str | None) -> str:
    """The title as it is searched: bracketed parts (`(Radio Edit)`) and a featuring tail dropped."""
    text = _BRACKETS.sub(' ', title or '')
    text = _FEAT.sub('', text)
    return ' '.join(text.split())


def clean_artist(artist: str | None) -> str:
    """The first credited artist: `Armin van Buuren & Davina Michelle` searches as `Armin van Buuren`."""
    text = _FEAT.sub('', ' ' + (artist or '').strip()).strip()
    first = _ARTIST_SPLIT.split(text, maxsplit=1)[0] if text else ''
    return ' '.join(first.split())


def lookup_key(artist: str | None, title: str | None) -> str | None:
    """The cache key of a song: a SHA-256 of its normalised first artist and title, None when either is empty."""
    artist_part = _fold(clean_artist(artist))
    title_part = _fold(clean_title(title))
    if not artist_part or not title_part:
        return None
    return hashlib.sha256(f'{artist_part}\t{title_part}'.encode()).hexdigest()


# ----------------------------------------------------------------------------- the API


@dataclass(frozen=True)
class Lookup:
    """What GetSongBPM said about one song. `status` is `ok` or `not_found`."""

    key: str
    artist: str
    title: str
    status: str
    bpm: float | None = None
    song_id: str | None = None
    song_url: str | None = None


class Throttled(Exception):
    """GetSongBPM refused for load (HTTP 429): stop asking for the rest of this pass."""


class KeyRejected(Exception):
    """GetSongBPM refused the API key: stop asking until the key changes."""


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


def _default_http_get(url: str, params: dict[str, str]) -> tuple[int, Any]:
    """`GET url?params` -> (status, parsed JSON or None). Raises on network trouble."""
    import requests  # pylint: disable=import-outside-toplevel

    response = requests.get(url, params=params, timeout=TIMEOUT_SECONDS, headers={'User-Agent': user_agent()})
    try:
        return response.status_code, response.json()
    except ValueError:
        return response.status_code, None


def _tempo(value: Any) -> float | None:
    """A listed tempo as a float when it is a plausible one: `"128"`, `128`, `"127.5"`."""
    try:
        number = float(str(value).strip().replace(',', '.'))
    except (TypeError, ValueError):
        return None
    return number if VALID_MIN <= number <= VALID_MAX else None


def _same_artist(wanted: str, listed: str) -> bool:
    """True when the listed artist is the wanted one, or one names the other as a whole word run."""
    if not wanted or not listed:
        return False
    return wanted == listed or f' {wanted} ' in f' {listed} ' or f' {listed} ' in f' {wanted} '


def parse_search(body: Any, artist: str, title: str) -> tuple[float, str | None, str | None] | None:
    """(tempo, song id, song page) of the first result that is this song, or None.

    Tolerant on purpose: `search` is a list of songs, or an object with an `error` ("no result")
    when nothing matched; a song's `tempo` is a string or a number; `artist` is an object with a
    `name`. A result counts when its title is the searched title and its artist the searched
    artist, both normalised. Anything else in the body is ignored.
    """
    if not isinstance(body, dict):
        return None
    results = body.get('search')
    if not isinstance(results, list):
        return None
    wanted_title = _fold(clean_title(title))
    wanted_artist = _fold(clean_artist(artist))
    for item in results:
        if not isinstance(item, dict):
            continue
        listed_artist = item.get('artist')
        name = listed_artist.get('name') if isinstance(listed_artist, dict) else listed_artist
        if _fold(clean_title(str(item.get('title') or ''))) != wanted_title:
            continue
        if not _same_artist(wanted_artist, _fold(str(name or ''))):
            continue
        tempo = _tempo(item.get('tempo'))
        if tempo is None:
            continue
        song_id = str(item['id'])[:64] if item.get('id') else None
        uri = str(item['uri'])[:512] if isinstance(item.get('uri'), str) else None
        return tempo, song_id, uri
    return None


def _refused_key(status: int, body: Any) -> bool:
    """True when the answer says the API key is wrong or missing."""
    if status in (401, 403):
        return True
    error = body.get('error') if isinstance(body, dict) else None
    return isinstance(error, str) and 'key' in error.lower()


def fetch(artist: str, title: str, api_key: str, http_get=None, pace: _Pace | None = None) -> Lookup | None:
    """Ask GetSongBPM about one song. None on a transient failure.

    Raises `Throttled` on HTTP 429 and `KeyRejected` when the key is refused.
    """
    key = lookup_key(artist, title)
    if key is None:
        return None
    search_artist, search_title = clean_artist(artist), clean_title(title)
    params = {'api_key': api_key, 'type': 'both', 'lookup': f'song:{search_title} artist:{search_artist}'}
    (pace or _PACE).wait()
    try:
        status, body = (http_get or _default_http_get)(API_URL, params)
    except Exception as exc:  # pylint: disable=broad-except  # the lookup is optional
        # Only the type: the client's message can hold the URL, and the URL holds the key.
        logger.info('bpm: GetSongBPM not reachable (%s)', type(exc).__name__)
        return None
    if status == 429:
        raise Throttled('GetSongBPM refused for load (HTTP 429)')
    if _refused_key(status, body):
        raise KeyRejected(f'GetSongBPM refused the API key (HTTP {status})')
    if status >= 400 or not isinstance(body, dict):
        logger.info('bpm: GetSongBPM answered HTTP %s', status)
        return None
    found = parse_search(body, artist, title)
    stored_artist, stored_title = search_artist[:255], search_title[:255]
    if found is None:
        return Lookup(key, stored_artist, stored_title, NOT_FOUND)
    tempo, song_id, uri = found
    return Lookup(key, stored_artist, stored_title, OK, round(tempo, 2), song_id, uri)


# ----------------------------------------------------------------------------- the cache

#: Every cached key with its status and age: what a pass need not ask again.
KNOWN_SQL = 'SELECT lookup_key, status, fetched_at FROM getsongbpm_lookups'
#: The tempos the octave choice may use.
TEMPOS_SQL = "SELECT lookup_key, bpm FROM getsongbpm_lookups WHERE status = 'ok' AND bpm IS NOT NULL"
UPSERT_SQL = """
    INSERT INTO getsongbpm_lookups (lookup_key, artist, title, status, bpm, song_id, song_url, fetched_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE artist = VALUES(artist), title = VALUES(title), status = VALUES(status),
        bpm = VALUES(bpm), song_id = VALUES(song_id), song_url = VALUES(song_url), fetched_at = VALUES(fetched_at)
"""

#: Measured tracks under a mainstream folder, newest first, with what a lookup and the weak-prior
#: test need. `{paths}` is one `mf.file_path LIKE %s` per mainstream root (fixed SQL).
CANDIDATES_SQL = """
    SELECT t.id AS track_id, t.title, a.name AS artist_name, t.primary_artist_id,
           (SELECT GROUP_CONCAT(tl.label_id) FROM library_track_labels tl
            WHERE tl.track_id = t.id) AS labels,
           (SELECT mf.file_path FROM library_media_files mf WHERE mf.track_id = t.id
            ORDER BY mf.id LIMIT 1) AS file_path
    FROM library_track_bpm b
    JOIN library_tracks t ON t.track_uid = b.track_uid
    JOIN library_artists a ON a.id = t.primary_artist_id
    WHERE b.status = 'ok' AND t.title IS NOT NULL
      AND EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id AND ({paths}))
    ORDER BY t.id DESC
"""


def candidates_sql(music_root: str = octave.MUSIC_ROOT) -> tuple[str, list[str]]:
    """CANDIDATES_SQL with one LIKE per mainstream root, and its parameters."""
    roots = sorted(octave.MAINSTREAM_ROOTS)
    paths = ' OR '.join(['mf.file_path LIKE %s'] * len(roots))
    prefix = music_root.rstrip('/')
    return CANDIDATES_SQL.format(paths=paths), [f'{prefix}/{root}/%' for root in roots]


def _rows(connect: Callable[[], Any], sql: str, params: Iterable = ()) -> list[dict]:
    conn = connect()
    if not conn:
        raise RuntimeError('database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(sql, list(params))
            return list(cursor.fetchall())
    finally:
        conn.close()


def load_tempos(connect: Callable[[], Any]) -> dict[str, float]:
    """Every cached GetSongBPM tempo by lookup key."""
    return {str(row['lookup_key']): float(row['bpm']) for row in _rows(connect, TEMPOS_SQL)}


def store(connect: Callable[[], Any], lookup: Lookup, now: datetime) -> None:
    """Upsert one answer into `getsongbpm_lookups`."""
    conn = connect()
    if not conn:
        raise RuntimeError('database connection failed')
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                UPSERT_SQL,
                (
                    lookup.key,
                    lookup.artist,
                    lookup.title,
                    lookup.status,
                    lookup.bpm,
                    lookup.song_id,
                    lookup.song_url,
                    now.replace(microsecond=0, tzinfo=None),
                ),
            )
        conn.commit()
    finally:
        conn.close()


def due_keys(known: Iterable[dict], now: datetime) -> set[str]:
    """The keys of KNOWN_SQL rows that need no asking: found, or a miss younger than the retry age."""
    settled: set[str] = set()
    cutoff = now - timedelta(days=NOT_FOUND_RETRY_DAYS)
    for row in known:
        fetched = row.get('fetched_at')
        if row.get('status') == OK or (isinstance(fetched, datetime) and fetched.replace(tzinfo=None) >= cutoff):
            settled.add(str(row['lookup_key']))
    return settled


def evidence_prior(
    row: Mapping[str, Any], evidence: octave.Evidence, tempos: Mapping[str, float]
) -> octave.Prior | None:
    """The GetSongBPM prior of one track: its cached tempo when its priors are weak, else None."""
    if not tempos or not octave.weak_priors(evidence):
        return None
    key = lookup_key(row.get('artist_name'), row.get('title'))
    tempo = tempos.get(key) if key else None
    return None if tempo is None else octave.Prior.around(tempo, octave.EXTERNAL_SPREAD)


@dataclass
class PassResult:
    """What one lookup pass asked and found."""

    asked: int = 0
    found: int = 0
    not_found: int = 0
    stopped: str | None = None
    #: Track ids whose song GetSongBPM now lists: their octave is chosen again at once.
    track_ids: list[int] = field(default_factory=list)
    tempos: dict[str, float] = field(default_factory=dict)


def lookup_pass(
    connect: Callable[[], Any],
    priors: Any,
    api_key: str,
    now: datetime,
    *,
    budget: int = PASS_BUDGET,
    http_get=None,
    pace: _Pace | None = None,
) -> PassResult:
    """Ask GetSongBPM about up to `budget` songs of weak-prior mainstream tracks, newest first.

    `priors` is the analyzer's `priors.Priors`; a track with a usable label or artist prior is
    skipped. Every answer is stored; the tracks of found songs are returned for a refold.
    """
    # pylint: disable-next=import-outside-toplevel  # refold imports this module
    from services.music_manager.bpm.refold import evidence_from

    result = PassResult()
    if not api_key or budget <= 0:
        return result
    settled = due_keys(_rows(connect, KNOWN_SQL), now)
    sql, params = candidates_sql()
    tracks_by_key: dict[str, list[int]] = {}
    queue: list[tuple[str, dict]] = []
    for row in _rows(connect, sql, params):
        if not octave.weak_priors(evidence_from(row, priors)):
            continue
        key = lookup_key(row.get('artist_name'), row.get('title'))
        if key is None or key in settled:
            continue
        if key not in tracks_by_key:
            tracks_by_key[key] = []
            queue.append((key, row))
        tracks_by_key[key].append(int(row['track_id']))
    for key, row in queue[:budget]:
        try:
            found = fetch(str(row.get('artist_name') or ''), str(row.get('title') or ''), api_key, http_get, pace)
        except (Throttled, KeyRejected) as exc:
            logger.warning('bpm: %s; no more GetSongBPM lookups this pass', exc)
            result.stopped = type(exc).__name__
            break
        result.asked += 1
        if found is None:
            continue
        store(connect, found, now)
        if found.status == OK and found.bpm is not None:
            result.found += 1
            result.tempos[key] = found.bpm
            result.track_ids.extend(tracks_by_key[key])
        else:
            result.not_found += 1
    return result
