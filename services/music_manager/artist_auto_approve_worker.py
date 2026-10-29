"""The scheduled artist evidence run: `tools/artist_auto_approve.py`, once a day, inside music-manager.

The artist curation queue only shrinks when someone decides a name. Since the queue was
wired to the tagger (docs/designs/artist-curation/technical.md, "Wiring the queue") a
name the scanner records is *pending* -- not trusted by any artist rule -- until it is
approved, and in the first thirty days 8 of ~3.300 new names were. The evidence run
that approved 5.903 names in one go had been run once, by hand. This loop runs it on a
schedule, bounded, with the tool's own judgement (services/common/Helpers/ArtistEvidence.py
is that judgement, shared by both).

One round:

1. **New names first**: every pending name (undecided, not grandfathered in
   `rules_artist_legacy_trust`) the run has no current verdict for, newest first.
2. **Then a slice of the backlog**: undecided grandfathered names without a current
   verdict, most tracks first, `artist_auto_approve_backlog_slice` of them.
   Both together never exceed `artist_auto_approve_max_names`, and the round stops at
   `artist_auto_approve_max_minutes` however much is left; the next round continues.
3. Each name is resolved against Deezer, iTunes Search and MusicBrainz exactly as the
   tool does (`resolve`), at each source's documented rate (`MIN_INTERVAL`: MusicBrainz
   1.1 s, iTunes 3.2 s, Deezer 0.25 s), and its verdict is stored in
   `rules_artist_evidence`.
4. **Apply** (not in a dry run): every stored `approve` verdict not yet applied, for a
   name still undecided, is approved in `rules_artists` signed `auto-external` -- the
   same rows `POST /api/rules/artists/decide` writes. Approvals a dry run judged are
   applied by the first round after the dry run is switched off.
5. One INFO line on `music-manager.artist-auto-approve` for the round, and a row in
   `rules_artist_evidence_runs`.

What a verdict is not: a decision. Nothing is ever rejected automatically. A name a
curator undid after the run approved it (`applied_at` set, no decision any more) is never
looked up or approved again -- the undo is a human's answer. A name the evidence did not
clear is looked up again after `artist_auto_approve_recheck_days`; a name a source failed
to answer for (`incomplete`) on the next round.

Settings (Beheer > Config, group "Artist curation") are read at every check, so a change
applies without a restart. Dry run is on by default: see the design for why.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

from services.common.config_store import ConfigStore
from services.common.Helpers.ArtistEvidence import (
    APPROVE,
    DECIDED_BY,
    DEEZER,
    INCOMPLETE,
    MIN_INTERVAL,
    POLICY,
    RETRIES,
    SKIPPED,
    SOURCES,
    TIMEOUT,
    UNRESOLVED,
    Verdict,
    _deezer_error,
    fold,
    resolve,
    titles_hash,
    user_agent,
)
from services.music_manager.database import get_db_connection, transaction
from services.music_manager.thread_registry import default_stale_after, run_forever

logger = logging.getLogger('music-manager.artist-auto-approve')

#: The name under which the loop appears in `/health` `threads`.
THREAD_NAME = 'artist-auto-approve'
#: How often the loop wakes up to see whether a round is due (or the switch changed).
CHECK_EVERY_SECONDS = 3600
#: A round may take `max_minutes` (three hours by default) and a check happens hourly, so
#: the heartbeat is judged on the daily cadence, never on the hourly one.
STALE_AFTER_SECONDS = default_stale_after(24 * 3600)
#: Names approved per transaction.
APPLY_BATCH = 100
#: Artist ids per title query.
TITLE_CHUNK = 500
#: What a name gets when the tagger already rewrites or drops it (`rules_ignored_artists`):
#: approving it would delete that rule, which is a curation decision, not evidence.
TAGGER_RULE = 'tagger-rule'

DEFAULTS: dict[str, Any] = {
    'enabled': True,
    'dry_run': True,
    'interval_hours': 24,
    'backlog_slice': 300,
    'max_names': 1000,
    'max_minutes': 180,
    'recheck_days': 90,
}

#: Set to end the loop (and a round in progress, between two requests).
stop_event = threading.Event()


# ----------------------------------------------------------------------------- settings


def _positive_int(value: Any, default: int, *, allow_zero: bool = False) -> int:
    """`value` as a positive (or, with `allow_zero`, non-negative) integer, else `default`."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return default
    if number > 0 or (allow_zero and number == 0):
        return number
    return default


def _flag(value: Any, default: bool) -> bool:
    """A boolean setting; strings from the environment read the way a person would mean them."""
    if value is None:
        return default
    if isinstance(value, str):
        return value.strip().lower() not in ('0', 'false', 'no', 'off', '')
    return bool(value)


def settings_snapshot(settings: Any = None) -> dict[str, Any]:
    """The loop's settings, validated, as this check will use them."""
    settings = settings if settings is not None else ConfigStore()

    def get(key: str) -> Any:
        return settings.get(f'artist_auto_approve_{key}')

    return {
        'enabled': _flag(get('enabled'), DEFAULTS['enabled']),
        'dry_run': _flag(get('dry_run'), DEFAULTS['dry_run']),
        'interval_seconds': 3600 * _positive_int(get('interval_hours'), DEFAULTS['interval_hours']),
        'backlog_slice': _positive_int(get('backlog_slice'), DEFAULTS['backlog_slice'], allow_zero=True),
        'max_names': _positive_int(get('max_names'), DEFAULTS['max_names']),
        'max_seconds': 60 * _positive_int(get('max_minutes'), DEFAULTS['max_minutes']),
        'recheck_days': _positive_int(get('recheck_days'), DEFAULTS['recheck_days']),
    }


# ----------------------------------------------------------------------------- fetching


class RateLimitedFetcher:
    """GET with a per-source minimum interval, retries and a stop switch; answers cached for one round.

    The tool's `Fetcher` caches into its sqlite file and sleeps with `time.sleep`; this one
    keeps its cache in memory (the verdicts are what persists) and pauses through `wait`,
    which is the stop event's `wait` in production: a pause returns early, and the round
    ends, as soon as the loop is told to stop. `clock` and `wait` are injectable so tests
    can prove the intervals without sleeping.
    """

    def __init__(
        self,
        session: Any,
        *,
        clock: Callable[[], float] = time.monotonic,
        wait: Callable[[float], bool] | None = None,
        min_interval: dict[str, float] | None = None,
        retries: int = RETRIES,
        timeout: float = TIMEOUT,
    ):
        self.session = session
        self.clock = clock
        self.wait = wait if wait is not None else stop_event.wait
        self.min_interval = dict(MIN_INTERVAL if min_interval is None else min_interval)
        self.retries = retries
        self.timeout = timeout
        self.last_call: dict[str, float] = {}
        self.cache: dict[tuple[str, str], dict] = {}
        self.requests = 0
        self.fetched = 0
        self.failed = 0
        self.stopped = False

    def get(self, source: str, url: str) -> dict | None:
        """The parsed body, or None when the source did not answer (counted in `failed`)."""
        key = (source, url)
        if key in self.cache:
            return self.cache[key]
        if not self.stopped:
            status, body = self._fetch(source, url)
            if status == 200:
                try:
                    parsed = json.loads(body)
                except ValueError:
                    parsed = None
                if isinstance(parsed, dict):
                    self.cache[key] = parsed
                    self.fetched += 1
                    return parsed
        self.failed += 1
        return None

    def _pause(self, seconds: float) -> bool:
        """Wait `seconds` unless told to stop; True when the round has to end."""
        if seconds > 0 and self.wait(seconds):
            self.stopped = True
        return self.stopped

    def _fetch(self, source: str, url: str) -> tuple[int, str]:
        """One answer from `source`, honouring its interval; (0, '') when it never came."""
        for attempt in range(self.retries):
            last = self.last_call.get(source)
            if last is not None and self._pause(self.min_interval.get(source, 1.0) - (self.clock() - last)):
                return 0, ''
            self.last_call[source] = self.clock()
            self.requests += 1
            try:
                response = self.session.get(url, timeout=self.timeout)
            except Exception as error:  # pylint: disable=broad-except  # network; retried
                logger.debug('%s: %s (%s)', source, error, url)
                if self._pause(2**attempt):
                    return 0, ''
                continue
            status, body = response.status_code, response.text
            if source == DEEZER and status == 200 and _deezer_error(body):
                status = 429
            if status in (429, 503):
                retry_after = str(response.headers.get('Retry-After', ''))
                if self._pause(float(retry_after) if retry_after.isdigit() else 2 ** (attempt + 1)):
                    return 0, ''
                continue
            return status, body
        return 0, ''


def _default_session() -> Any:
    """A requests session carrying the tool's User-Agent (MusicBrainz refuses anonymous clients)."""
    import requests  # pylint: disable=import-outside-toplevel  # only the loop needs it

    session = requests.Session()
    session.headers['User-Agent'] = user_agent()
    return session


# ----------------------------------------------------------------------------- storage

#: Undecided names with tracks that have no current verdict. A verdict is current when it
#: is under this POLICY and either `approve`, or less than `recheck_days` old and not
#: `incomplete`. A name whose approval was applied is never selected again: if it is
#: undecided now, a curator undid it, and that is the answer.
_CANDIDATES = """
    FROM library_artists a
    LEFT JOIN rules_artists r ON r.name = a.name
    LEFT JOIN rules_artist_legacy_trust l ON l.name = a.name
    LEFT JOIN rules_artist_evidence e ON e.name = a.name
    WHERE r.name IS NULL
      AND EXISTS (SELECT 1 FROM library_track_artists la WHERE la.artist_id = a.id)
      AND NOT EXISTS (SELECT 1 FROM rules_ignored_artists i WHERE i.name = a.name)
      AND (e.name IS NULL OR (e.applied_at IS NULL AND (
            e.policy <> %s OR e.verdict = 'incomplete'
            OR (e.verdict <> 'approve' AND e.checked_at < NOW() - INTERVAL %s DAY))))
"""
NEW_NAMES_SQL = f'SELECT a.id, a.name {_CANDIDATES} AND l.name IS NULL ORDER BY a.id DESC LIMIT %s'
BACKLOG_SQL = (
    'SELECT a.id, a.name, (SELECT COUNT(*) FROM library_track_artists lc WHERE lc.artist_id = a.id) AS track_count '
    f'{_CANDIDATES} AND l.name IS NOT NULL ORDER BY track_count DESC, a.name LIMIT %s'
)
REMAINING_SQL = f'SELECT COUNT(*) AS n {_CANDIDATES}'
TITLES_SQL = (
    'SELECT la.artist_id, t.title FROM library_track_artists la JOIN library_tracks t ON t.id = la.track_id '
    'WHERE la.artist_id IN ({placeholders})'
)
IGNORED_SQL = 'SELECT name FROM rules_ignored_artists'
LAST_ROUND_SQL = 'SELECT id, TIMESTAMPDIFF(SECOND, started_at, NOW()) AS age FROM rules_artist_evidence_runs ORDER BY id DESC LIMIT 1'
START_ROUND_SQL = 'INSERT INTO rules_artist_evidence_runs (dry_run) VALUES (%s)'
FINISH_ROUND_SQL = """
    UPDATE rules_artist_evidence_runs SET finished_at = NOW(), new_names = %s, backlog_names = %s,
        approved = %s, applied = %s, unresolved = %s, skipped = %s, incomplete = %s,
        requests = %s, failed_requests = %s, stopped_early = %s
    WHERE id = %s
"""
RECORD_VERDICT_SQL = """
    INSERT INTO rules_artist_evidence (name, policy, titles_hash, verdict, rule, evidence, run_id, checked_at)
    VALUES (%s, %s, %s, %s, %s, %s, %s, NOW())
    ON DUPLICATE KEY UPDATE policy = VALUES(policy), titles_hash = VALUES(titles_hash), verdict = VALUES(verdict),
        rule = VALUES(rule), evidence = VALUES(evidence), run_id = VALUES(run_id), checked_at = NOW()
"""
#: Stored approvals still to apply: under this policy, never applied, name still undecided.
PENDING_APPROVALS_SQL = """
    SELECT e.name FROM rules_artist_evidence e LEFT JOIN rules_artists r ON r.name = e.name
    WHERE e.verdict = 'approve' AND e.policy = %s AND e.applied_at IS NULL AND r.name IS NULL
    ORDER BY e.checked_at, e.name LIMIT %s
"""
DECIDED_AMONG_SQL = 'SELECT name FROM rules_artists WHERE name IN ({placeholders})'
MARK_APPLIED_SQL = 'UPDATE rules_artist_evidence SET applied_at = NOW() WHERE name IN ({placeholders})'


def _placeholders(values: list) -> str:
    """`%s, %s, ...` for an IN list of `values`."""
    return ', '.join(['%s'] * len(values))


def _in_list_sql(template: str, values: list) -> str:
    """`template` with its `{placeholders}` filled by one `%s` per value; the values stay bound parameters."""
    return template.format(placeholders=_placeholders(values))


@dataclass
class Candidate:
    """One name a round looks up: its library id, spelling and whether it is new (pending) or backlog."""

    artist_id: int
    name: str
    new: bool


class EvidenceStore:
    """Every database read and write of a round, on short pooled connections.

    A round lasts minutes to hours and is almost all waiting on the network, so no
    connection is held across it: each method takes one from the pool and gives it back.
    """

    def __init__(self, connect: Callable[[], Any] = get_db_connection):
        self._connect_factory = connect

    def _connect(self) -> Any:
        conn = self._connect_factory()
        if not conn:
            raise RuntimeError('Database connection failed')
        return conn

    def _rows(self, sql: str, params: tuple | list = ()) -> list[dict]:
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(sql, params)
                return list(cursor.fetchall())
        finally:
            conn.close()

    def seconds_since_last_round(self) -> int | None:
        """Seconds since the last round started, by the database clock; None before the first."""
        rows = self._rows(LAST_ROUND_SQL)
        return int(rows[0]['age']) if rows else None

    def start_round(self, dry_run: bool) -> int:
        """Open the ledger row of a new round and return its id."""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(START_ROUND_SQL, (1 if dry_run else 0,))
                return int(cursor.lastrowid)
        finally:
            conn.close()

    def finish_round(self, round_id: int, result: RoundResult) -> None:
        """Close the ledger row with the round's counts."""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    FINISH_ROUND_SQL,
                    (
                        result.new_names,
                        result.backlog_names,
                        result.verdicts[APPROVE],
                        result.applied,
                        result.verdicts[UNRESOLVED],
                        result.verdicts[SKIPPED],
                        result.verdicts[INCOMPLETE],
                        result.requests,
                        result.failed_requests,
                        1 if result.stopped_early else 0,
                        round_id,
                    ),
                )
        finally:
            conn.close()

    def candidates(self, max_names: int, backlog_slice: int, recheck_days: int) -> list[Candidate]:
        """New names first (newest first), then up to `backlog_slice` backlog names; `max_names` in all."""
        new = [
            Candidate(int(row['id']), row['name'], True)
            for row in self._rows(NEW_NAMES_SQL, (POLICY, recheck_days, max_names))
        ]
        room = min(backlog_slice, max_names - len(new))
        backlog = []
        if room > 0:
            backlog = [
                Candidate(int(row['id']), row['name'], False)
                for row in self._rows(BACKLOG_SQL, (POLICY, recheck_days, room))
            ]
        return new + backlog

    def remaining(self, recheck_days: int) -> int:
        """How many names still have no current verdict -- the work left, for the summary."""
        rows = self._rows(REMAINING_SQL, (POLICY, recheck_days))
        return int(rows[0]['n']) if rows else 0

    def titles(self, artist_ids: list[int]) -> dict[int, list[str]]:
        """Every local title per artist id."""
        out: dict[int, list[str]] = {artist_id: [] for artist_id in artist_ids}
        for start in range(0, len(artist_ids), TITLE_CHUNK):
            chunk = artist_ids[start : start + TITLE_CHUNK]
            for row in self._rows(_in_list_sql(TITLES_SQL, chunk), chunk):
                out.setdefault(int(row['artist_id']), []).append(row['title'] or '')
        return out

    def ignored_keys(self) -> set[str]:
        """`fold` of every name the tagger already rewrites or drops."""
        return {fold(row['name']) for row in self._rows(IGNORED_SQL)}

    def record_verdict(self, name: str, hashed: str, verdict: Verdict, round_id: int) -> None:
        """Store (or replace) the verdict for `name`."""
        conn = self._connect()
        try:
            with conn.cursor() as cursor:
                cursor.execute(
                    RECORD_VERDICT_SQL,
                    (name, POLICY, hashed, verdict.verdict, verdict.rule, json.dumps(verdict.evidence), round_id),
                )
        finally:
            conn.close()

    def pending_approvals(self, limit: int) -> list[str]:
        """Stored `approve` verdicts not yet applied, for names still undecided, oldest first."""
        return [row['name'] for row in self._rows(PENDING_APPROVALS_SQL, (POLICY, limit))]

    def apply_approvals(self, names: list[str]) -> list[str]:
        """Approve `names` signed auto-external, in batches; returns the ones actually approved.

        Each batch is one transaction that first drops any name decided meanwhile, so a
        curator's decision taken during the round is never overwritten.
        """
        from services.music_manager.routers.artist_curation import (  # pylint: disable=import-outside-toplevel
            record_approvals,  # the router imports nothing from here; importing late keeps startup light
        )

        applied: list[str] = []
        for start in range(0, len(names), APPLY_BATCH):
            batch = names[start : start + APPLY_BATCH]
            conn = self._connect()
            try:
                with transaction(conn), conn.cursor() as cursor:
                    cursor.execute(_in_list_sql(DECIDED_AMONG_SQL, batch), batch)
                    decided = {row['name'] for row in cursor.fetchall()}
                    batch = [name for name in batch if name not in decided]
                    if batch:
                        record_approvals(cursor, batch, DECIDED_BY)
                        cursor.execute(_in_list_sql(MARK_APPLIED_SQL, batch), batch)
            finally:
                conn.close()
            applied.extend(batch)
        return applied


# ----------------------------------------------------------------------------- the round


@dataclass
class RoundResult:
    """What one round did, for the ledger row and the summary line."""

    dry_run: bool
    new_names: int = 0
    backlog_names: int = 0
    verdicts: dict[str, int] = field(
        default_factory=lambda: dict.fromkeys((APPROVE, UNRESOLVED, SKIPPED, INCOMPLETE), 0)
    )
    approvable: int = 0
    applied: int = 0
    requests: int = 0
    failed_requests: int = 0
    stopped_early: bool = False
    remaining: int = 0
    seconds: float = 0.0


def run_round(
    config: dict[str, Any],
    *,
    store: EvidenceStore | None = None,
    fetcher: Any = None,
    clock: Callable[[], float] = time.monotonic,
    resolver: Callable[..., Verdict] = resolve,
    stop: threading.Event | None = None,
    refresh: Callable[[], None] | None = None,
) -> RoundResult:
    """One bounded evidence round: look names up, store verdicts, apply approvals unless dry run.

    `resolver` is the tool's `resolve` -- the decision rules are not re-implemented here,
    only called. Everything else is injectable for the tests.
    """
    store = store or EvidenceStore()
    stop = stop or stop_event
    fetcher = fetcher if fetcher is not None else RateLimitedFetcher(_default_session(), clock=clock, wait=stop.wait)
    started = clock()
    deadline = started + config['max_seconds']
    result = RoundResult(dry_run=config['dry_run'])
    round_id = store.start_round(config['dry_run'])

    candidates = store.candidates(config['max_names'], config['backlog_slice'], config['recheck_days'])
    titles = store.titles([candidate.artist_id for candidate in candidates]) if candidates else {}
    ignored = store.ignored_keys() if candidates else set()
    for candidate in candidates:
        if stop.is_set() or clock() >= deadline:
            result.stopped_early = True
            break
        own_titles = titles.get(candidate.artist_id, [])
        if fold(candidate.name) in ignored:
            verdict = Verdict(SKIPPED, TAGGER_RULE, {'reason': 'the tagger already rewrites or drops this name'})
        else:
            try:
                verdict = resolver(fetcher, candidate.name, own_titles, SOURCES)
            except Exception:  # pylint: disable=broad-except  # one name must not end the round
                logger.debug('%s: lookup failed', candidate.name, exc_info=True)
                continue
        if getattr(fetcher, 'stopped', False):
            # Told to stop in the middle of this name: its evidence is partial and the
            # next round asks again, so nothing is stored for it.
            result.stopped_early = True
            break
        store.record_verdict(candidate.name, titles_hash(own_titles), verdict, round_id)
        result.verdicts[verdict.verdict] += 1
        if candidate.new:
            result.new_names += 1
        else:
            result.backlog_names += 1

    pending = store.pending_approvals(config['max_names'])
    result.approvable = len(pending)
    if not config['dry_run'] and pending:
        ignored = store.ignored_keys()
        applied = store.apply_approvals([name for name in pending if fold(name) not in ignored])
        result.applied = len(applied)
        if applied:
            (refresh or _refresh_trust)()

    result.requests = int(getattr(fetcher, 'requests', 0))
    result.failed_requests = int(getattr(fetcher, 'failed', 0))
    result.remaining = store.remaining(config['recheck_days'])
    result.seconds = clock() - started
    store.finish_round(round_id, result)
    _log_summary(round_id, result)
    return result


def _refresh_trust() -> None:
    """Let the running tagger see the new approvals at once (as `decide` does)."""
    from services.music_manager.routers.artist_curation import (  # pylint: disable=import-outside-toplevel
        refresh_artist_trust,
    )

    refresh_artist_trust()


def _log_summary(round_id: int, result: RoundResult) -> None:
    """The one INFO line per round that shows in the event log what the run did."""
    if result.dry_run:
        outcome = f'dry run, {result.approvable} approvable name(s) waiting, none approved'
    else:
        outcome = f'approved {result.applied} name(s) signed {DECIDED_BY}'
    logger.info(
        'Artist auto-approve round %d: looked up %d new and %d backlog name(s) in %.0fs '
        '(approve %d, unresolved %d, skipped %d, incomplete %d; %d request(s), %d failed)%s; %s; %d name(s) left to look up',
        round_id,
        result.new_names,
        result.backlog_names,
        result.seconds,
        result.verdicts[APPROVE],
        result.verdicts[UNRESOLVED],
        result.verdicts[SKIPPED],
        result.verdicts[INCOMPLETE],
        result.requests,
        result.failed_requests,
        ', stopped at its bound' if result.stopped_early else '',
        outcome,
        result.remaining,
    )


# ----------------------------------------------------------------------------- the loop


def auto_approve_tick(
    settings: Any = None,
    *,
    store: EvidenceStore | None = None,
    round_runner: Callable[..., RoundResult] = run_round,
) -> float:
    """One check: run a round when the switch is on and the previous round is `interval` old.

    Returns the seconds until the next check -- an hour, or less when the next round is
    due sooner. A database failure raises, so `run_forever` logs it and backs off.
    """
    config = settings_snapshot(settings)
    if not config['enabled']:
        logger.debug('%s: switched off on the config page', THREAD_NAME)
        return CHECK_EVERY_SECONDS
    store = store or EvidenceStore()
    age = store.seconds_since_last_round()
    if age is not None and age < config['interval_seconds']:
        return float(min(CHECK_EVERY_SECONDS, config['interval_seconds'] - age))
    round_runner(config, store=store)
    return CHECK_EVERY_SECONDS


def run_artist_auto_approve(stop: threading.Event | None = None) -> None:
    """The `artist-auto-approve` thread: check hourly, run a round when one is due."""
    run_forever(
        THREAD_NAME,
        auto_approve_tick,
        CHECK_EVERY_SECONDS,
        stale_after=STALE_AFTER_SECONDS,
        stop=stop or stop_event,
    )
