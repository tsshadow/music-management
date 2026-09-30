"""The BPM analysis worker: measure every track's tempo, newest first, and keep it measured.

docs/designs/bpm-browse/technical.md, "Worker". Runs as its own container (`bpm-analyzer` in
docker/docker-compose.yml, from the tools image), not inside music-manager: it needs ffmpeg,
which music-manager's image does not have, and its CPU and memory have a hard ceiling from
compose rather than competing with the API's threads.

One round:

1. Ask for up to `BATCH_SIZE` tracks without a current measurement (`DUE_SQL`), highest track
   id -- newest -- first, so a fresh download is measured within a round or two and the backlog
   follows. A measurement is current while the file's size and mtime match and the method is
   `estimator.METHOD`; a failure is retried after `RETRY_FAILED_AFTER`, at most `MAX_ATTEMPTS`
   times, or at once when the file changed. Sets, podcasts and anything longer than the
   configured maximum are skipped: a mix has no one tempo.
2. Decode a `bpm_analysis_excerpt_seconds` excerpt from 30% into each file with ffmpeg (a seek,
   so the CIFS mount only serves the excerpt), at 11025 Hz mono, and estimate it
   (`estimator.estimate_bpm`) in a pool of `bpm_analysis_workers` processes at the lowest CPU
   and I/O priority.
3. Fold each estimate into the band of the track's genres -- or, without any, of its primary
   artist's commonest genre -- and store it in `library_track_bpm`.
4. Bring those tracks' rows in `library_track_effective_bpm` up to date (`effective_table.sync`),
   so the library table and the analytics see a new measurement within the round.

Besides the rounds, every `EFFECTIVE_SYNC_SECONDS` -- also while the analysis is paused or off --
the whole `library_track_effective_bpm` table is synced, which picks up changed genres, a changed
`bpm_reliable_confidence` and deleted tracks (issue #141).

Resumable by construction: the queue is whatever has no current row, so a restart, a pause or a
crash simply continues. Settings are re-read from music-manager's config file every round
(`read_settings`), so Beheer → Config → BPM takes effect without a restart. Progress goes to a
small JSON status file that music-manager's /health reports (`status.py`), and an INFO summary
every `SUMMARY_SECONDS`.
"""

from __future__ import annotations

import contextlib
import json
import logging
import os
import signal
import subprocess
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import Executor, ProcessPoolExecutor
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

import numpy as np

from services.music_manager.bpm import effective_table, estimator
from services.music_manager.bpm.bands import band_for_genres, fold_into_band

logger = logging.getLogger('music-manager.bpm')

BATCH_SIZE = 48
#: Sleep between rounds when there is nothing to measure; new downloads wait at most this long.
IDLE_SECONDS = 300.0
#: Sleep while switched off or paused.
OFF_SECONDS = 60.0
SUMMARY_SECONDS = 600.0
#: How often the whole effective-BPM table is synced; a failed sync is retried after IDLE_SECONDS.
EFFECTIVE_SYNC_SECONDS = 1800.0
RETRY_FAILED_AFTER = timedelta(days=7)
MAX_ATTEMPTS = 3
DECODE_TIMEOUT_SECONDS = 120
#: Where into a track the excerpt starts: past the intro, before the outro.
EXCERPT_START = 0.3

STATUS_PATH = Path(os.getenv('BPM_ANALYZER_STATUS', '/app/state/status.json'))
CONFIG_PATH = Path(os.getenv('CONFIG_PATH', 'data/config.json'))

stop_event = threading.Event()


# ----------------------------------------------------------------------------- settings

#: (key, type, default) of every setting the worker reads; the same keys and defaults as the
#: BPM group in services/common/config_store.py, which the config page edits.
SETTINGS: tuple[tuple[str, str, Any], ...] = (
    ('bpm_analysis_enabled', 'boolean', True),
    ('bpm_analysis_paused', 'boolean', False),
    ('bpm_analysis_workers', 'integer', 2),
    ('bpm_analysis_excerpt_seconds', 'integer', 60),
    ('bpm_analysis_skip_forms', 'string', 'set,liveset,podcast'),
    ('bpm_analysis_max_minutes', 'integer', 15),
    # Not an analysis setting, but it decides the stored effective confidence (effective.py).
    ('bpm_reliable_confidence', 'integer', 75),
)
_BOUNDS = {
    'bpm_analysis_workers': (1, 8),
    'bpm_analysis_excerpt_seconds': (20, 180),
    'bpm_analysis_max_minutes': (1, 60),
    'bpm_reliable_confidence': (0, 100),
}


def _coerce(kind: str, value: Any, default: Any) -> Any:
    """`value` as the setting's type, or `default` when it cannot be read as one."""
    if value is None:
        return default
    if kind == 'boolean':
        if isinstance(value, str):
            return value.strip().lower() not in ('0', 'false', 'no', 'off', '')
        return bool(value)
    if kind == 'integer':
        try:
            return int(value)
        except (TypeError, ValueError):
            return default
    return str(value)


def read_settings(config_path: Path = CONFIG_PATH, env: dict | None = None) -> dict[str, Any]:
    """The worker's settings: the config page's override, else the environment, else the default.

    Read from music-manager's `config.json` directly (mounted read-only), not through
    ConfigStore: that is a process-wide singleton that reads the file once, and this process
    lives for weeks while the file changes under it.
    """
    env = os.environ if env is None else env
    try:
        overrides = json.loads(Path(config_path).read_text(encoding='utf-8'))
        if not isinstance(overrides, dict):
            overrides = {}
    except (OSError, ValueError):
        overrides = {}
    values: dict[str, Any] = {}
    for key, kind, default in SETTINGS:
        raw = overrides.get(key, env.get(key.upper()))
        value = _coerce(kind, raw, default)
        if key in _BOUNDS:
            low, high = _BOUNDS[key]
            value = min(high, max(low, value))
        values[key] = value
    values['skip_forms'] = sorted(
        {form.strip().lower() for form in values['bpm_analysis_skip_forms'].split(',') if form.strip()}
    )
    return values


# ----------------------------------------------------------------------------- SQL

#: Tracks without a current measurement, newest first. `{forms}` is one `%s` per skipped form
#: (never empty: a blank sentinel is always appended). Parameters: the forms, the maximum
#: duration, the current method, the failure retry cutoff, the attempt ceiling, the limit.
DUE_SQL = """
    SELECT t.id AS track_id, t.track_uid, t.duration_secs,
           mf.file_path, mf.file_mtime, mf.file_size
    FROM library_tracks t
    JOIN library_media_files mf
      ON mf.id = (SELECT MIN(m2.id) FROM library_media_files m2 WHERE m2.track_id = t.id)
    LEFT JOIN library_track_bpm b ON b.track_uid = t.track_uid
    WHERE t.track_uid IS NOT NULL
      AND (t.form IS NULL OR t.form NOT IN ({forms}))
      AND (t.duration_secs IS NULL OR t.duration_secs <= %s)
      AND (
        b.track_uid IS NULL
        OR (b.status = 'ok' AND (b.method <> %s
                                 OR NOT (b.file_mtime <=> mf.file_mtime)
                                 OR NOT (b.file_size <=> mf.file_size)))
        OR (b.status = 'failed' AND (NOT (b.file_mtime <=> mf.file_mtime)
                                     OR NOT (b.file_size <=> mf.file_size)
                                     OR (b.analyzed_at < %s AND b.attempts < %s)))
      )
    ORDER BY t.id DESC
    LIMIT %s
"""

#: The same queue, counted, for the progress summary.
REMAINING_SQL = (
    'SELECT COUNT(*) AS remaining FROM (' + DUE_SQL.replace('ORDER BY t.id DESC\n    LIMIT %s', '') + ') AS due'
)

#: The genres of a set of tracks. `{placeholders}`: one `%s` per track id.
GENRES_SQL = """
    SELECT tg.track_id, g.name
    FROM library_track_genres tg
    JOIN rules_genres g ON g.id = tg.genre_id
    WHERE tg.track_id IN ({placeholders})
"""

#: For tracks without genres of their own: every genre on the other tracks of their primary
#: artist, with how often, so the commonest can stand in.
ARTIST_GENRES_SQL = """
    SELECT t.id AS track_id, g.name, COUNT(*) AS uses
    FROM library_tracks t
    JOIN library_tracks o ON o.primary_artist_id = t.primary_artist_id AND o.id <> t.id
    JOIN library_track_genres tg ON tg.track_id = o.id
    JOIN rules_genres g ON g.id = tg.genre_id
    WHERE t.id IN ({placeholders}) AND t.primary_artist_id IS NOT NULL
    GROUP BY t.id, g.name
"""

UPSERT_SQL = """
    INSERT INTO library_track_bpm
        (track_uid, status, bpm, raw_bpm, confidence, method, octave_corrected,
         file_mtime, file_size, attempts, error, analyzed_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, 1, %s, %s)
    ON DUPLICATE KEY UPDATE
        attempts = IF(VALUES(status) = 'failed' AND status = 'failed', attempts + 1, 1),
        status = VALUES(status),
        bpm = VALUES(bpm),
        raw_bpm = VALUES(raw_bpm),
        confidence = VALUES(confidence),
        method = VALUES(method),
        octave_corrected = VALUES(octave_corrected),
        file_mtime = VALUES(file_mtime),
        file_size = VALUES(file_size),
        error = VALUES(error),
        analyzed_at = VALUES(analyzed_at)
"""


def _in_list_sql(template: str, count: int, name: str = 'placeholders') -> str:
    """`template` with `{name}` filled by `count` `%s` markers; the values stay bound parameters."""
    return template.format(**{name: ', '.join(['%s'] * count)})


def _due_params(config: dict, now: datetime, limit: int | None) -> tuple[str, list]:
    """The queue statement and its parameters; `limit=None` gives the counting variant."""
    forms = [*config['skip_forms'], '']
    params: list = [
        *forms,
        config['bpm_analysis_max_minutes'] * 60,
        estimator.METHOD,
        now - RETRY_FAILED_AFTER,
        MAX_ATTEMPTS,
    ]
    if limit is None:
        return _in_list_sql(REMAINING_SQL, len(forms), 'forms'), params
    return _in_list_sql(DUE_SQL, len(forms), 'forms'), [*params, limit]


class BpmStore:
    """Every statement the worker runs, one short-lived connection per call."""

    def __init__(self, connect: Callable[[], Any] | None = None):
        if connect is None:
            from services.music_manager.database import get_db_connection  # pylint: disable=import-outside-toplevel

            connect = get_db_connection
        self._connect_fn = connect

    def _rows(self, sql: str, params: Iterable) -> list[dict]:
        conn = self._connect_fn()
        if not conn:
            raise RuntimeError('database connection failed')
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, list(params))
                return list(cursor.fetchall())
        finally:
            conn.close()

    def due_tracks(self, config: dict, now: datetime, limit: int = BATCH_SIZE) -> list[dict]:
        """Up to `limit` tracks to measure, newest first."""
        sql, params = _due_params(config, now, limit)
        return self._rows(sql, params)

    def remaining(self, config: dict, now: datetime) -> int:
        """How many tracks the queue holds right now."""
        sql, params = _due_params(config, now, None)
        rows = self._rows(sql, params)
        return int(rows[0]['remaining']) if rows else 0

    def genres_for(self, track_ids: list[int]) -> dict[int, list[str]]:
        """Each track's genres, or its primary artist's commonest genre when it has none."""
        if not track_ids:
            return {}
        genres: dict[int, list[str]] = {}
        for row in self._rows(_in_list_sql(GENRES_SQL, len(track_ids)), track_ids):
            genres.setdefault(int(row['track_id']), []).append(row['name'])
        missing = [track_id for track_id in track_ids if track_id not in genres]
        if missing:
            best: dict[int, tuple[int, str]] = {}
            for row in self._rows(_in_list_sql(ARTIST_GENRES_SQL, len(missing)), missing):
                track_id, uses = int(row['track_id']), int(row['uses'])
                if track_id not in best or uses > best[track_id][0]:
                    best[track_id] = (uses, row['name'])
            for track_id, (_, name) in best.items():
                genres[track_id] = [name]
        return genres

    def sync_effective(self, track_ids: list[int] | None, reliable_confidence: float) -> effective_table.SyncResult:
        """Sync `library_track_effective_bpm`, for every track (None) or the given ones."""
        return effective_table.sync(self._connect_fn, track_ids=track_ids, reliable_confidence=reliable_confidence)

    def save(self, rows: list[tuple]) -> None:
        """Upsert one batch of UPSERT_SQL rows."""
        if not rows:
            return
        conn = self._connect_fn()
        if not conn:
            raise RuntimeError('database connection failed')
        try:
            with conn.cursor() as cursor:
                cursor.executemany(UPSERT_SQL, rows)
            conn.commit()
        finally:
            conn.close()


# ----------------------------------------------------------------------------- analysis


class DecodeError(RuntimeError):
    """ffmpeg could not produce audio from the file."""


def excerpt_window(duration: float | None, excerpt_seconds: float) -> tuple[float, float]:
    """(offset, seconds) of the excerpt to decode: from 30% in, never past the end."""
    if not duration or duration <= 0:
        return 0.0, float(excerpt_seconds)
    if duration <= excerpt_seconds:
        return 0.0, float(duration)
    return round(min(duration * EXCERPT_START, duration - excerpt_seconds), 2), float(excerpt_seconds)


def decode_excerpt(path: str, offset: float, seconds: float, run: Callable = subprocess.run) -> np.ndarray:
    """Mono float32 samples at estimator.SAMPLE_RATE, decoded by ffmpeg from `offset` for `seconds`.

    `-ss` before `-i` seeks in the container rather than decoding from the start, so only the
    excerpt is read from the mount.
    """
    command = [
        'ffmpeg', '-nostdin', '-hide_banner', '-v', 'error',
        '-ss', f'{offset:.2f}', '-t', f'{seconds:.2f}', '-i', path,
        '-vn', '-ac', '1', '-ar', str(estimator.SAMPLE_RATE), '-f', 'f32le', 'pipe:1',
    ]  # fmt: skip
    try:
        result = run(command, capture_output=True, timeout=DECODE_TIMEOUT_SECONDS, check=False)
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise DecodeError(f'ffmpeg: {exc}') from exc
    if result.returncode != 0 or not result.stdout:
        message = (result.stderr or b'').decode('utf-8', 'replace').strip().splitlines()
        raise DecodeError(f'ffmpeg exit {result.returncode}: {message[-1] if message else "no audio"}')
    return np.frombuffer(result.stdout, dtype=np.float32)


def analyze(job: dict, excerpt_seconds: float) -> dict:
    """Decode and estimate one track; never raises (a failure is a result too). Runs in the pool."""
    try:
        offset, seconds = excerpt_window(job.get('duration_secs'), excerpt_seconds)
        found = estimator.estimate_bpm(decode_excerpt(job['file_path'], offset, seconds))
        return {'track_id': job['track_id'], 'ok': True, 'raw': found.bpm, 'confidence': found.confidence}
    except Exception as exc:  # pylint: disable=broad-except  # one bad file must not end the batch
        return {'track_id': job['track_id'], 'ok': False, 'error': f'{type(exc).__name__}: {exc}'[:255]}


def lower_priority() -> None:
    """Pool initializer: the lowest CPU priority, and idle I/O class where ionice exists."""
    with contextlib.suppress(OSError):
        os.nice(19)
    with contextlib.suppress(OSError, subprocess.TimeoutExpired):
        subprocess.run(['ionice', '-c', '3', '-p', str(os.getpid())], check=False, capture_output=True, timeout=5)


def to_row(job: dict, result: dict, genres: list[str], now: datetime) -> tuple:
    """The UPSERT_SQL row for one analysed track, folded into its genre's band."""
    common = (job['file_mtime'], job['file_size'])
    if not result.get('ok'):
        return (job['track_uid'], 'failed', None, None, None, estimator.METHOD, 0, *common, result.get('error'), now)
    folded = fold_into_band(result['raw'], band_for_genres(genres))
    confidence = float(result['confidence'])
    if not folded.in_band:
        confidence *= 0.5
    return (
        job['track_uid'],
        'ok',
        folded.bpm,
        result['raw'],
        round(confidence, 3),
        estimator.METHOD,
        int(folded.octave_corrected),
        *common,
        None,
        now,
    )


# ----------------------------------------------------------------------------- the loop


@dataclass
class Progress:
    """Counters since the process started, and what the status file last said."""

    started: float = field(default_factory=time.time)
    analyzed: int = 0
    failed: int = 0
    remaining: int | None = None
    state: str = 'starting'
    last_summary: float = 0.0
    #: When the last full effective-BPM sync ran (clock time), 0 before the first.
    effective_synced_at: float = 0.0
    effective_tracks: int | None = None
    window: list[tuple[float, int]] = field(default_factory=list)

    def rate_per_hour(self, now: float) -> float | None:
        """Tracks per hour over the last hour of rounds, None before there is any."""
        recent = [(t, n) for t, n in self.window if now - t <= 3600]
        self.window = recent
        if not recent:
            return None
        span = max(now - recent[0][0], 60.0)
        return round(sum(n for _, n in recent) * 3600 / span, 1)


def write_status(progress: Progress, config: dict, path: Path = STATUS_PATH, now: float | None = None) -> None:
    """Write the status file music-manager's /health reads, atomically."""
    now = time.time() if now is None else now
    rate = progress.rate_per_hour(now)
    eta = round(progress.remaining / rate, 1) if rate and progress.remaining is not None else None
    payload = {
        'heartbeat_at': now,
        'state': progress.state,
        'analyzed': progress.analyzed,
        'failed': progress.failed,
        'remaining': progress.remaining,
        'rate_per_hour': rate,
        'eta_hours': eta,
        'workers': config.get('bpm_analysis_workers'),
        'method': estimator.METHOD,
        'started_at': progress.started,
        'effective_synced_at': progress.effective_synced_at or None,
        'effective_tracks': progress.effective_tracks,
    }
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix('.tmp')
        tmp.write_text(json.dumps(payload), encoding='utf-8')
        os.replace(tmp, path)
    except OSError as exc:
        logger.debug('bpm: could not write the status file %s: %s', path, exc)


class Worker:
    """Rounds of `BATCH_SIZE` tracks until stopped; see the module docstring."""

    def __init__(
        self,
        store: BpmStore,
        *,
        settings: Callable[[], dict] = read_settings,
        analyze_fn: Callable[[dict, float], dict] = analyze,
        pool_factory: Callable[[int], Executor] | None = None,
        status: Callable[[Progress, dict], None] = write_status,
        clock: Callable[[], float] = time.time,
        now: Callable[[], datetime] = datetime.now,
        stop: threading.Event | None = None,
    ):
        self.store = store
        self.settings = settings
        self.analyze_fn = analyze_fn
        self.pool_factory = pool_factory or (
            lambda workers: ProcessPoolExecutor(max_workers=workers, initializer=lower_priority)
        )
        self.status = status
        self.clock = clock
        self.now = now
        self.stop = stop or stop_event
        self.progress = Progress(started=clock())
        self._pool: Executor | None = None
        self._pool_size = 0
        self._next_full_sync = 0.0

    def _executor(self, workers: int) -> Executor:
        """The pool, recreated when the configured size changed."""
        if self._pool is None or workers != self._pool_size:
            if self._pool is not None:
                self._pool.shutdown(wait=True)
            self._pool = self.pool_factory(workers)
            self._pool_size = workers
        return self._pool

    def close(self) -> None:
        """Shut the pool down."""
        if self._pool is not None:
            self._pool.shutdown(wait=True, cancel_futures=True)
            self._pool = None

    def run_round(self, config: dict) -> int:
        """Measure one batch; returns how many tracks it handled (0 when the queue is empty)."""
        jobs = self.store.due_tracks(config, self.now())
        if not jobs:
            return 0
        genres = self.store.genres_for([job['track_id'] for job in jobs])
        excerpt = float(config['bpm_analysis_excerpt_seconds'])
        pool = self._executor(config['bpm_analysis_workers'])
        results = list(pool.map(self.analyze_fn, jobs, [excerpt] * len(jobs)))
        stamp = self.now().replace(microsecond=0)
        rows = [
            to_row(job, result, genres.get(job['track_id'], []), stamp)
            for job, result in zip(jobs, results, strict=True)
        ]
        self.store.save(rows)
        self._sync_effective(config, [job['track_id'] for job in jobs])
        failed = sum(1 for result in results if not result.get('ok'))
        self.progress.analyzed += len(jobs) - failed
        self.progress.failed += failed
        self.progress.window.append((self.clock(), len(jobs)))
        return len(jobs)

    def _sync_effective(self, config: dict, track_ids: list[int] | None = None) -> None:
        """Sync the effective-BPM table: in full when due (`track_ids` None), else for those tracks.

        A failure is logged and never ends the round: the measurements are stored either way, and
        the next full sync repairs whatever a failed partial one missed.
        """
        now = self.clock()
        if track_ids is None and now < self._next_full_sync:
            return
        reliable = config.get('bpm_reliable_confidence', 75) / 100.0
        try:
            result = self.store.sync_effective(track_ids, reliable)
        except Exception:  # pylint: disable=broad-except  # the table is derived; the next sync repairs it
            logger.exception('bpm: syncing the effective BPM table failed')
            if track_ids is None:
                self._next_full_sync = now + IDLE_SECONDS
            return
        if track_ids is not None:
            return
        self._next_full_sync = now + EFFECTIVE_SYNC_SECONDS
        self.progress.effective_synced_at = now
        self.progress.effective_tracks = result.resolved
        if result.upserted or result.deleted:
            logger.info(
                'bpm: effective BPM synced for %d tracks (%d updated, %d removed)',
                result.resolved,
                result.upserted,
                result.deleted,
            )

    def _summary(self, config: dict, force: bool = False) -> None:
        """Count the queue and log one INFO line, at most every SUMMARY_SECONDS."""
        now = self.clock()
        if not force and now - self.progress.last_summary < SUMMARY_SECONDS:
            return
        self.progress.last_summary = now
        self.progress.remaining = self.store.remaining(config, self.now())
        rate = self.progress.rate_per_hour(now)
        logger.info(
            'bpm: analysed %d, failed %d since start, %s remaining%s',
            self.progress.analyzed,
            self.progress.failed,
            self.progress.remaining,
            f', {rate:.0f}/h' if rate else '',
        )

    def tick(self) -> float:
        """One step of the loop; returns how long to wait before the next."""
        config = self.settings()
        self._sync_effective(config)
        if not config['bpm_analysis_enabled'] or config['bpm_analysis_paused']:
            self.progress.state = 'disabled' if not config['bpm_analysis_enabled'] else 'paused'
            self.status(self.progress, config)
            return OFF_SECONDS
        handled = self.run_round(config)
        self.progress.state = 'running' if handled else 'idle'
        self._summary(config, force=not handled and self.progress.remaining != 0)
        self.status(self.progress, config)
        return 0.0 if handled else IDLE_SECONDS

    def run(self) -> None:
        """Tick until stopped; a failed tick (database down) backs off and carries on."""
        failures = 0
        try:
            while not self.stop.is_set():
                try:
                    delay = self.tick()
                    failures = 0
                except Exception:  # pylint: disable=broad-except  # the loop must outlive any one round
                    failures += 1
                    delay = min(10.0 * 2 ** (failures - 1), IDLE_SECONDS)
                    logger.exception('bpm: round failed (%d in a row), retrying in %.0fs', failures, delay)
                if delay and self.stop.wait(delay):
                    break
        finally:
            self.close()


def main() -> None:
    """Entry point of the `bpm-analyzer` container."""
    from services.common.Helpers.logging_setup import setup_logging  # pylint: disable=import-outside-toplevel

    setup_logging('bpm-analyzer')
    signal.signal(signal.SIGTERM, lambda *_: stop_event.set())
    logger.info('bpm: analysis worker starting (method %s)', estimator.METHOD)
    Worker(BpmStore()).run()


if __name__ == '__main__':
    main()
