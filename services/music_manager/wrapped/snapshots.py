"""Stored Wrapped tabs (`wrapped_snapshots`): read one, compute it once, keep it.

The rules are in docs/designs/wrapped-page/technical.md ("Snapshots and caching"):

1. A row is fresh when its format is the code's and the period was closed when it was
   computed, or it is less than a day old.
2. A missing or stale row is computed under a lock per key, so two tabs opening at once
   compute once; the second finds the first one's row.
3. A closed period is frozen until `POST /api/wrapped/refresh` or a new format.
4. Custom ranges older than 30 days are deleted by the events-retention pass (`prune`).
"""

from __future__ import annotations

import json
import logging
import threading
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from services.music_manager.wrapped.payload import LIBRARY, WRAPPED_FORMAT, build_payload
from services.music_manager.wrapped.periods import Period

logger = logging.getLogger('music-manager.wrapped')

FRESH_FOR = timedelta(hours=24)
CUSTOM_RANGE_DAYS = 30

READ_SQL = """
    SELECT payload, closed, generated_at, format
    FROM wrapped_snapshots
    WHERE scope = %s AND username = %s AND period_key = %s AND tz = %s
"""

WRITE_SQL = """
    INSERT INTO wrapped_snapshots (scope, username, period_key, tz, data_until, closed, generated_at, format, payload)
    VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE data_until = VALUES(data_until), closed = VALUES(closed),
        generated_at = VALUES(generated_at), format = VALUES(format), payload = VALUES(payload)
"""

# Custom range keys hold an underscore; LIKE needs it escaped, as '_' matches any character.
PRUNE_SQL = "DELETE FROM wrapped_snapshots WHERE period_key LIKE '%%\\_%%' AND generated_at < %s"

_locks_guard = threading.Lock()
_locks: dict[tuple, threading.Lock] = {}


def _lock_for(key: tuple) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(key, threading.Lock())


def snapshot_key(kind: str, username: str | None, period: Period, zone: ZoneInfo) -> tuple[str, str, str, str]:
    """The primary key of a tab: the username is '' for the Library tab."""
    return kind, '' if kind == LIBRARY else (username or '').lower(), period.key, str(zone.key)


def is_fresh(row: dict | None, now: datetime) -> bool:
    """Rule 1: the right format, and closed or younger than a day."""
    if not row or int(row.get('format') or 0) != WRAPPED_FORMAT:
        return False
    if row.get('closed'):
        return True
    generated = row['generated_at']
    if generated.tzinfo is None:
        generated = generated.replace(tzinfo=UTC)
    return now - generated < FRESH_FOR


def read(cursor, key: tuple) -> dict | None:
    """The stored row of a key, or None."""
    cursor.execute(READ_SQL, key)
    return cursor.fetchone()


def write(cursor, key: tuple, payload: dict, period: Period, zone: ZoneInfo, now: datetime) -> None:
    """Store a computed tab under its key, replacing an older one."""
    end = period.end_utc(zone)
    naive_now = now.astimezone(UTC).replace(tzinfo=None)
    cursor.execute(
        WRITE_SQL,
        (
            *key,
            min(naive_now, end),
            1 if naive_now >= end else 0,
            naive_now,
            WRAPPED_FORMAT,
            json.dumps(payload, default=str, separators=(',', ':')),
        ),
    )


def get_or_compute(connect, kind: str, username: str | None, period: Period, zone: ZoneInfo, now=None) -> dict:
    """The tab for this key: the stored one when fresh, else computed now and stored.

    `connect` opens a database connection; the computation runs on its own one, so a caller
    that gave up waiting (the 503 path) does not hold it.
    """
    now = now or datetime.now(UTC)
    key = snapshot_key(kind, username, period, zone)
    conn = connect()
    if not conn:
        raise RuntimeError('Database connection failed')
    try:
        with conn.cursor() as cursor:
            row = read(cursor, key)
            if row is not None and is_fresh(row, now):
                return json.loads(row['payload'])
        with _lock_for(key):
            with conn.cursor() as cursor:
                row = read(cursor, key)
                if row is not None and is_fresh(row, now):
                    return json.loads(row['payload'])
                started = datetime.now(UTC)
                payload = build_payload(cursor, kind, username, period, zone, now)
                write(cursor, key, payload, period, zone, now)
            conn.commit()
            logger.info(
                'Computed Wrapped %s %s (%s) in %.1fs',
                kind,
                period.key,
                zone.key,
                (datetime.now(UTC) - started).total_seconds(),
            )
            return payload
    finally:
        conn.close()


DROP_SELECT_SQL = 'SELECT scope, username, period_key, tz FROM wrapped_snapshots WHERE scope = %s AND period_key = %s'


def drop(cursor, kind: str, period: Period, username: str | None = None) -> list[tuple]:
    """Delete the stored rows of a period (one account's, or all), returning their keys."""
    sql, params = DROP_SELECT_SQL, [kind, period.key]
    if username is not None:
        sql += ' AND username = %s'
        params.append(username.lower())
    cursor.execute(sql, tuple(params))
    keys = [(r['scope'], r['username'], r['period_key'], r['tz']) for r in cursor.fetchall() or []]
    for key in keys:
        cursor.execute(
            'DELETE FROM wrapped_snapshots WHERE scope = %s AND username = %s AND period_key = %s AND tz = %s', key
        )
    return keys


def prune(conn, now: datetime | None = None) -> int:
    """Rule 4: delete custom ranges computed more than 30 days ago. Returns the rows removed."""
    now = now or datetime.now(UTC)
    cutoff = (now - timedelta(days=CUSTOM_RANGE_DAYS)).astimezone(UTC).replace(tzinfo=None)
    with conn.cursor() as cursor:
        cursor.execute(PRUNE_SQL, (cutoff,))
        removed = cursor.rowcount or 0
    conn.commit()
    return removed
