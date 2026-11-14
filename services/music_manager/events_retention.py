"""Daily clean-up of the `events` table, with a window per level and a size cap.

Errors stay long enough to recognise a pattern; INFO goes quickly, because that is the
volume. Bug report 072 measured what "volume" means on production: 17.5 million rows,
6.9 GB, almost all of it one importer WARNING repeated for every unplaceable folder on
every cycle. The old pass did delete -- but a 60-day WARNING window over ~380.000
WARNINGs a day holds over 20 million rows, and nothing capped that.

How a pass works:

- Per level, oldest first: pick up to `BATCH_SIZE` ids through the `(level, created_at)`
  index, delete exactly those ids by primary key, commit, pause briefly. Deleting by
  primary key locks only the rows that go, never a range of the index that inserts are
  also writing to, and each statement is bounded by `STATEMENT_TIMEOUT_SECONDS`.
- The whole pass stops at `MAX_RUN_SECONDS`, however much is left, and asks
  `run_forever` to come back in `RETRY_SOONER_SECONDS` instead of a day. A backlog of
  millions is worked off over a few hourly passes, never by one long one.
- Then the size cap: if the table still holds more than `events_max_rows`, the oldest
  DEBUG rows go first, then INFO, WARNING and ERROR. CRITICAL is never removed by size.
- One summary line per pass at INFO on `music-manager.events-retention`, so the event
  log itself shows whether retention keeps up.

Deliberately absent: `OPTIMIZE TABLE`. InnoDB does not hand the space of deleted rows
back to the filesystem, but rebuilding a multi-gigabyte table locks it and doubles the
disk use while it runs; reclaiming space is an operator step, see the operator's runbook.
"""

from __future__ import annotations

import logging
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field

from services.common.config_store import EVENTS_RETENTION_DEFAULT_DAYS
from services.common.config_store import ConfigStore as Settings
from services.music_manager.database import get_db_connection
from services.music_manager.rbac import purge_refresh_tokens
from services.music_manager.thread_registry import run_forever

logger = logging.getLogger('music-manager.events-retention')

#: Levels in the order the age pass handles them: the noise first, so a pass that hits
#: its time bound has spent that time where the rows are.
LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR', 'CRITICAL')
#: What the size cap may remove, in this order. CRITICAL is missing on purpose.
SIZE_CAP_LEVELS = ('DEBUG', 'INFO', 'WARNING', 'ERROR')
DEFAULT_MAX_ROWS = 10_000_000

BATCH_SIZE = 10_000
BATCH_PAUSE_SECONDS = 0.2
STATEMENT_TIMEOUT_SECONDS = 30
MAX_RUN_SECONDS = 300.0
INTERVAL_SECONDS = 86400
RETRY_SOONER_SECONDS = 3600

_SELECT_EXPIRED = (
    'SELECT id FROM events WHERE level = %s AND created_at < DATE_SUB(NOW(3), INTERVAL %s DAY) '
    'ORDER BY created_at LIMIT %s'
)
_SELECT_OLDEST = 'SELECT id FROM events WHERE level = %s ORDER BY created_at LIMIT %s'
_DELETE_IDS = 'SET STATEMENT max_statement_time={timeout} FOR DELETE FROM events WHERE id IN ({placeholders})'
#: InnoDB's estimate: free, and only used to decide whether an exact count is worth it.
_ESTIMATE_ROWS = (
    "SELECT TABLE_ROWS AS n FROM information_schema.TABLES WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = 'events'"
)
_COUNT_ROWS = 'SELECT COUNT(*) AS n FROM events'


@dataclass
class PurgeResult:
    """What one retention pass did: rows removed per level, by age and by size, and whether it finished."""

    by_age: dict[str, int] = field(default_factory=dict)
    by_size: dict[str, int] = field(default_factory=dict)
    complete: bool = True
    seconds: float = 0.0

    @property
    def total(self) -> int:
        """Every row this pass removed."""
        return sum(self.by_age.values()) + sum(self.by_size.values())


def _positive_int(value) -> int:
    """`value` as a non-negative integer, or 0 for anything empty, invalid or below zero."""
    try:
        number = int(value)
    except (TypeError, ValueError):
        return 0
    return max(number, 0)


def retention_days(settings=None) -> dict[str, int]:
    """The configured window per level, falling back to the default for an empty or zero setting."""
    settings = settings or Settings()
    return {
        level: _positive_int(settings.get(f'events_retention_{level.lower()}_days'))
        or EVENTS_RETENTION_DEFAULT_DAYS[level]
        for level in LEVELS
    }


def max_rows(settings=None) -> int:
    """The configured size cap; 0 switches it off."""
    settings = settings or Settings()
    return _positive_int(settings.get('events_max_rows', DEFAULT_MAX_ROWS))


def _first(row):
    """The first column of a result row, from a DictCursor or a plain one."""
    if row is None:
        return None
    if isinstance(row, dict):
        return next(iter(row.values()))
    return row[0]


def _delete_batches(conn, select_sql, params, limit, deadline, clock, sleep) -> tuple[int, bool]:
    """Delete up to `limit` rows chosen by `select_sql`, one bounded batch at a time.

    Returns the rows removed and whether the selection ran dry (True) rather than
    stopping at the deadline or at `limit`.
    """
    removed = 0
    while removed < limit:
        if clock() >= deadline:
            return removed, False
        want = int(min(BATCH_SIZE, limit - removed))
        with conn.cursor() as cursor:
            cursor.execute(select_sql, (*params, want))
            ids = [_first(row) for row in cursor.fetchall()]
        if not ids:
            return removed, True
        sql = _DELETE_IDS.format(timeout=STATEMENT_TIMEOUT_SECONDS, placeholders=', '.join(['%s'] * len(ids)))
        with conn.cursor() as cursor:
            cursor.execute(sql, ids)
            removed += int(cursor.rowcount or 0)
        conn.commit()
        if len(ids) < want:
            return removed, True
        sleep(BATCH_PAUSE_SECONDS)
    return removed, False


def _row_count(conn, cap: int) -> int:
    """How many rows the table holds, counted exactly only when the estimate says it is over `cap`."""
    with conn.cursor() as cursor:
        cursor.execute(_ESTIMATE_ROWS)
        estimate = _positive_int(_first(cursor.fetchone()))
    if estimate <= cap:
        return estimate
    # TABLE_ROWS lags a mass delete until InnoDB recomputes its statistics, so acting on it
    # right after the age pass could remove millions of rows that are already gone. The
    # exact count reads the smallest index once, which is affordable exactly when it matters.
    with conn.cursor() as cursor:
        cursor.execute(_COUNT_ROWS)
        return _positive_int(_first(cursor.fetchone()))


def purge_once(
    conn,
    days: dict[str, int] | None = None,
    cap: int | None = None,
    *,
    max_seconds: float = MAX_RUN_SECONDS,
    clock: Callable[[], float] = time.monotonic,
    sleep: Callable[[float], None] = time.sleep,
) -> PurgeResult:
    """One retention pass over `events`: expired rows per level, then the size cap, within `max_seconds`."""
    days = days if days is not None else retention_days()
    cap = cap if cap is not None else max_rows()
    started = clock()
    deadline = started + max_seconds
    result = PurgeResult()

    for level in LEVELS:
        removed, dry = _delete_batches(
            conn, _SELECT_EXPIRED, (level, days[level]), float('inf'), deadline, clock, sleep
        )
        result.by_age[level] = removed
        if not dry:
            result.complete = False
            break

    if result.complete and cap:
        excess = _row_count(conn, cap) - cap
        for level in SIZE_CAP_LEVELS:
            if excess <= 0:
                break
            removed, dry = _delete_batches(conn, _SELECT_OLDEST, (level,), excess, deadline, clock, sleep)
            if removed:
                result.by_size[level] = removed
            excess -= removed
            if not dry and excess > 0:
                # Neither ran dry nor reached the excess: the deadline stopped it.
                result.complete = False
                break

    result.seconds = clock() - started
    _log_summary(result, cap)
    return result


def _log_summary(result: PurgeResult, cap: int) -> None:
    """The one line per pass that shows in the event log whether retention keeps up."""
    by_age = ', '.join(f'{level} {n}' for level, n in result.by_age.items() if n) or 'nothing'
    ending = 'done' if result.complete else f'stopped at the {MAX_RUN_SECONDS:.0f}s bound, next pass in 1h'
    logger.info(
        'Events retention: removed %d row(s) in %.1fs; by age: %s; %s',
        result.total,
        result.seconds,
        by_age,
        ending,
    )
    if result.by_size:
        # The cap only bites when something writes far more than the windows were sized
        # for, which is worth a look -- hence a WARNING, which also reaches the alerts topic.
        logger.warning(
            'Events retention: table was over its cap of %d rows, removed the oldest %s',
            cap,
            ', '.join(f'{n} {level}' for level, n in result.by_size.items()),
        )


def prune_wrapped_ranges(conn) -> None:
    """Delete stored Wrapped custom ranges older than 30 days; a failure is logged, not raised.

    Imported here rather than at the top: the Wrapped package pulls in the listening router, which
    this thread module has no other use for.
    """
    from services.music_manager.wrapped.snapshots import prune

    try:
        removed = prune(conn)
    except Exception as exc:
        logger.warning('Wrapped snapshot prune failed: %s', exc)
        return
    if removed:
        logger.info('Wrapped: removed %d stored custom range(s) older than 30 days', removed)


def retention_tick() -> float | None:
    """One purge of events and stale refresh tokens; raises on a database failure so run_forever can log it and back off.

    Returns `RETRY_SOONER_SECONDS` when the pass stopped at its time bound, so a backlog
    is worked off in hourly passes instead of one pass a day.
    """
    conn = get_db_connection()
    if not conn:
        return None
    try:
        result = purge_once(conn)
        # The same daily housekeeping pass caps user_refresh_tokens, which every login grows.
        purge_refresh_tokens(conn)
        # And the Wrapped custom ranges nobody computed for a month (wrapped/snapshots.py, rule 4).
        prune_wrapped_ranges(conn)
    finally:
        conn.close()
    return None if result.complete else RETRY_SOONER_SECONDS


def run_events_retention(stop: threading.Event | None = None) -> None:
    """The `events-retention` thread: purge on start, then once a day (hourly while a backlog lasts), for good.

    `stop` ends the loop when set (tests use it to run an exact number of rounds).
    """
    run_forever('events-retention', retention_tick, INTERVAL_SECONDS, stop=stop)
