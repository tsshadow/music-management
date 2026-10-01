"""The effective BPM of every track, materialised in `library_track_effective_bpm` for SQL readers.

docs/designs/bpm-browse/technical.md, "Effective BPM in SQL". `effective.resolve` is a Python
rule (a tag or tempo is folded into the band of the track's genres), so the library table's BPM
column and sort, its BPM filter and search term, the analytics histogram and the feeds cannot
compute it in SQL without writing that rule twice. Instead the bpm-analyzer worker resolves every
track here and stores the result; those readers join the table on its primary key
(`analytics_filters.EFFECTIVE_BPM_JOIN`) and never choose between the sources themselves.

Two ways in, both the same function:

- a full sync (`sync(connect)`) every `worker.EFFECTIVE_SYNC_SECONDS`, which also picks up a
  changed genre, a changed `bpm_reliable_confidence` and deleted tracks;
- a partial one (`sync(connect, track_ids=...)`) right after the worker stores a batch of
  measurements, so a new measurement reaches the library table within the round.

Only what changed is written: the current table is read first, each resolved row compared with
it, and the difference upserted (and rows whose track lost every source deleted). A sync that
finds nothing changed writes nothing. The inputs are streamed (an unbuffered cursor), so memory
holds the current table's ~300k small tuples, not the ~300k input rows as well.
"""

from __future__ import annotations

import logging
import sys
from collections.abc import Callable, Iterable, Iterator
from dataclasses import dataclass
from typing import Any

from services.music_manager.bpm.effective import DEFAULT_RELIABLE_CONFIDENCE, resolve_row
from services.music_manager.bpm.index import INPUTS_SQL

logger = logging.getLogger('music-manager.bpm')

TABLE = 'library_track_effective_bpm'
#: Rows per INSERT/DELETE statement.
WRITE_BATCH = 1000
#: Rows fetched per round trip from the unbuffered input cursor.
FETCH_BATCH = 2000

_INPUT_COLUMNS = (
    'track_id',
    'manual',
    'bpm_tag',
    'tempo',
    'measured',
    'measured_confidence',
    'measured_folded',
    'genres',
)

EXISTING_SQL = f'SELECT track_id, bpm, source, confidence, approximate, folded FROM {TABLE}'

UPSERT_SQL = f"""
    INSERT INTO {TABLE} (track_id, bpm, source, confidence, approximate, folded, updated_at)
    VALUES (%s, %s, %s, %s, %s, %s, NOW())
    ON DUPLICATE KEY UPDATE
        bpm = VALUES(bpm),
        source = VALUES(source),
        confidence = VALUES(confidence),
        approximate = VALUES(approximate),
        folded = VALUES(folded),
        updated_at = VALUES(updated_at)
"""

#: The part of a row a sync compares: (bpm, source, confidence, approximate, folded).
Value = tuple[float, str, str, int, int]


@dataclass(frozen=True)
class SyncResult:
    """What one sync did."""

    resolved: int
    upserted: int
    deleted: int


def _placeholders(count: int) -> str:
    """`count` comma-separated `%s` markers for an IN list; the values stay bound parameters."""
    return ', '.join(['%s'] * count)


def inputs_sql(track_ids: list[int] | None) -> str:
    """INPUTS_SQL over every track, or over the given ids (bound as parameters)."""
    if track_ids is None:
        return INPUTS_SQL.format(where='')
    return INPUTS_SQL.format(where=f'\n      AND t.id IN ({_placeholders(len(track_ids))})')


def _value(bpm: Any, source: str, confidence: str, approximate: Any, folded: Any) -> Value:
    """A row's comparable value; DECIMAL and TINYINT normalised so equal rows compare equal.

    The two words are interned: a full sync holds ~300k of these, and three sources and three
    confidences need not be 600k separate strings.
    """
    return (
        round(float(bpm), 2),
        sys.intern(str(source)),
        sys.intern(str(confidence)),
        int(bool(approximate)),
        int(bool(folded)),
    )


def _existing(cursor, track_ids: list[int] | None) -> dict[int, Value]:
    """The table as it is, for every track or the given ids."""
    if track_ids is None:
        cursor.execute(EXISTING_SQL)
    else:
        cursor.execute(f'{EXISTING_SQL} WHERE track_id IN ({_placeholders(len(track_ids))})', list(track_ids))
    found: dict[int, Value] = {}
    for row in cursor.fetchall():
        found[int(row['track_id'])] = _value(
            row['bpm'], row['source'], row['confidence'], row['approximate'], row['folded']
        )
    return found


def _stream(cursor, fetch_batch: int = FETCH_BATCH) -> Iterator[dict]:
    """The executed cursor's rows as dicts, `fetch_batch` at a time, whichever cursor class it is."""
    while True:
        chunk = cursor.fetchmany(fetch_batch)
        if not chunk:
            return
        for row in chunk:
            yield row if isinstance(row, dict) else dict(zip(_INPUT_COLUMNS, row, strict=False))


def diff(
    rows: Iterable[dict], existing: dict[int, Value], reliable_confidence: float
) -> tuple[list[tuple], list[int], int]:
    """(rows to upsert, track ids to delete, rows resolved) for input `rows` against `existing`.

    `existing` is consumed: whatever is left in it after the inputs had no usable tempo any more
    (or no inputs at all) and is to be deleted.
    """
    upserts: list[tuple] = []
    resolved = 0
    for row in rows:
        track_id = int(row['track_id'])
        found = resolve_row(row, reliable_confidence)
        if found is None:
            continue
        resolved += 1
        value = _value(found.bpm, found.source, found.confidence, found.approximate, found.folded)
        if existing.pop(track_id, None) != value:
            upserts.append((track_id, *value))
    return upserts, sorted(existing), resolved


def _write(conn, upserts: list[tuple], deletes: list[int], batch: int = WRITE_BATCH) -> None:
    """Upsert and delete in batches; each statement commits on its own (the pool autocommits)."""
    with conn.cursor() as cursor:
        for start in range(0, len(upserts), batch):
            cursor.executemany(UPSERT_SQL, upserts[start : start + batch])
        for start in range(0, len(deletes), batch):
            chunk = deletes[start : start + batch]
            cursor.execute(f'DELETE FROM {TABLE} WHERE track_id IN ({_placeholders(len(chunk))})', chunk)
    conn.commit()


def _unbuffered_cursor(conn):
    """A streaming cursor where pymysql provides one, else the connection's default cursor."""
    try:
        import pymysql.cursors  # pylint: disable=import-outside-toplevel

        cursor_class = pymysql.cursors.SSDictCursor
        if isinstance(cursor_class, type):
            return conn.cursor(cursor_class)
    except (ImportError, AttributeError):
        pass
    return conn.cursor()


def sync(
    connect: Callable[[], Any],
    *,
    track_ids: Iterable[int] | None = None,
    reliable_confidence: float = DEFAULT_RELIABLE_CONFIDENCE,
) -> SyncResult:
    """Bring `library_track_effective_bpm` up to date, for every track or only `track_ids`."""
    ids = None if track_ids is None else sorted({int(i) for i in track_ids})
    if ids is not None and not ids:
        return SyncResult(0, 0, 0)

    conn = connect()
    if not conn:
        raise RuntimeError('database connection failed')
    try:
        with conn.cursor() as cursor:
            existing = _existing(cursor, ids)
    finally:
        conn.close()

    conn = connect()
    if not conn:
        raise RuntimeError('database connection failed')
    try:
        cursor = _unbuffered_cursor(conn)
        try:
            cursor.execute(inputs_sql(ids), ids or [])
            upserts, deletes, resolved = diff(_stream(cursor), existing, reliable_confidence)
        finally:
            cursor.close()
    finally:
        conn.close()

    if upserts or deletes:
        conn = connect()
        if not conn:
            raise RuntimeError('database connection failed')
        try:
            _write(conn, upserts, deletes)
        finally:
            conn.close()
    return SyncResult(resolved=resolved, upserted=len(upserts), deleted=len(deletes))
