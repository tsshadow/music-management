"""Browse by BPM: the tracks at a tempo, and how the library spreads over tempos.

docs/designs/bpm-browse/technical.md, "API". Two endpoints under /api/library/bpm:

- `GET /tracks` -- the tracks at `bpm` +- `tol` (default: the `bpm_browse_tolerance` setting)
  or from `bpm_from` to `bpm_to`, optionally only `min_confidence` or better and only one
  genre, paged with `limit`/`offset`. Each track carries its effective BPM, where it came from
  and how far to trust it (services/music_manager/bpm/effective.py), and `library_path` for
  LMS's getSongsByPath, the way the feeds hand tracks to a player.
- `GET /histogram` -- track counts per whole BPM and the genres worth offering as a filter.

Both read the in-memory index (services/music_manager/bpm/index.py); the database is asked
only for the details of the page being returned.

And the manual override (bug report 140, docs/designs/bpm-octave/technical.md, "Manual override"),
for callers with the `bpm.override` permission:

- `PUT /tracks/{track_id}/manual` -- set the track's tempo by hand: `{"bpm": 128}`, or
  `{"factor": 0.5}` / `{"factor": 2}` to halve or double the tempo it shows now. Stored in
  `library_track_bpm_manual`, the effective BPM's first source; audited as `bpm.manual_set`.
- `DELETE /tracks/{track_id}/manual` -- back to the measured tempo; audited as `bpm.manual_cleared`.

Both answer with the track's effective BPM afterwards, and bring `library_track_effective_bpm`
along for that track at once (the library table, the feeds and the analytics read it).
"""

from __future__ import annotations

import json
import logging
from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from services.common.config_store import ConfigStore as Settings
from services.music_manager import rbac
from services.music_manager.bpm import effective_table
from services.music_manager.bpm.effective import DEFAULT_RELIABLE_CONFIDENCE, VALID_MAX, VALID_MIN, resolve_row
from services.music_manager.bpm.index import INDEX_SQL, INPUTS_SQL, BpmIndex, Entry, IndexCache
from services.music_manager.database import get_db_connection, require_connection
from services.music_manager.library_paths import relative_path
from services.music_manager.routers.users import verify_api_key

logger = logging.getLogger('music-manager.bpm')
router = APIRouter(tags=['bpm'])
settings = Settings()

DEFAULT_TOLERANCE = 2.0
MAX_TOLERANCE = 10.0
MAX_PAGE_SIZE = 500
#: The tempos the histogram and a range may span.
BPM_MIN = 40.0
BPM_MAX = 500.0

Confidence = Literal['low', 'medium', 'high']


def default_tolerance() -> float:
    """`bpm_browse_tolerance` from the config page, clamped to 0..MAX_TOLERANCE."""
    try:
        value = float(settings.get('bpm_browse_tolerance'))
    except (TypeError, ValueError):
        return DEFAULT_TOLERANCE
    return min(MAX_TOLERANCE, max(0.0, value))


def reliable_confidence() -> float:
    """`bpm_reliable_confidence` (a percentage) as 0..1."""
    try:
        value = float(settings.get('bpm_reliable_confidence'))
    except (TypeError, ValueError):
        return DEFAULT_RELIABLE_CONFIDENCE
    return min(1.0, max(0.0, value / 100.0))


def load_index() -> BpmIndex:
    """Read every track's BPM inputs and resolve them (INDEX_SQL)."""
    conn = require_connection(get_db_connection())
    try:
        with conn.cursor() as cursor:
            cursor.execute(INDEX_SQL)
            rows = cursor.fetchall()
    finally:
        conn.close()
    return BpmIndex.from_rows(rows, reliable_confidence=reliable_confidence())


index_cache = IndexCache(load_index)

#: The details of one page of tracks, by id. The ids come from the index, never from the caller.
DETAILS_SQL = """
    SELECT t.id, t.title, COALESCE(NULLIF(t.display_artist, ''), a.name) AS artist,
           t.duration_secs, t.work_id,
           (SELECT mf.file_path FROM library_media_files mf WHERE mf.track_id = t.id
            ORDER BY mf.id LIMIT 1) AS file_path
    FROM library_tracks t
    LEFT JOIN library_artists a ON a.id = t.primary_artist_id
    WHERE t.id IN ({placeholders})
"""


def _details_sql(ids: list[int]) -> str:
    """DETAILS_SQL with one `%s` per id; the ids themselves stay bound parameters."""
    return DETAILS_SQL.format(placeholders=', '.join(['%s'] * len(ids)))


def _details(ids: list[int]) -> dict[int, dict]:
    """Title, artist, duration and file per track id."""
    if not ids:
        return {}
    conn = require_connection(get_db_connection())
    try:
        with conn.cursor() as cursor:
            cursor.execute(_details_sql(ids), ids)
            return {int(row['id']): row for row in cursor.fetchall()}
    finally:
        conn.close()


def _track_view(entry: Entry, row: dict) -> dict:
    """One track as the API returns it."""
    return {
        'id': entry.track_id,
        'title': row.get('title'),
        'artist': row.get('artist'),
        'duration_secs': row.get('duration_secs'),
        'work_id': row.get('work_id'),
        'genres': list(entry.genres),
        # What a client hands LMS's getSongsByPath; see library_paths.relative_path.
        'library_path': relative_path(row.get('file_path')),
        'bpm': entry.bpm,
        'bpm_source': entry.source,
        'bpm_confidence': entry.confidence,
        'bpm_folded': entry.folded,
        'bpm_approximate': entry.approximate,
    }


def resolve_window(
    bpm: float | None, tol: float | None, bpm_from: float | None, bpm_to: float | None
) -> tuple[float, float, float | None, float | None]:
    """(from, to, center, tolerance) for a request: a picked tempo +- a tolerance, or a range."""
    if bpm is not None:
        tolerance = default_tolerance() if tol is None else tol
        return bpm - tolerance, bpm + tolerance, bpm, tolerance
    if bpm_from is None and bpm_to is None:
        raise HTTPException(status_code=400, detail='give bpm, or bpm_from and/or bpm_to')
    low = BPM_MIN if bpm_from is None else bpm_from
    high = BPM_MAX if bpm_to is None else bpm_to
    if low > high:
        raise HTTPException(status_code=400, detail='bpm_from is above bpm_to')
    return low, high, None, None


@router.get('/tracks')
def bpm_tracks(
    bpm: float | None = Query(None, ge=BPM_MIN, le=BPM_MAX),
    tol: float | None = Query(None, ge=0, le=MAX_TOLERANCE),
    bpm_from: float | None = Query(None, ge=BPM_MIN, le=BPM_MAX),
    bpm_to: float | None = Query(None, ge=BPM_MIN, le=BPM_MAX),
    min_confidence: Confidence = 'low',
    genre: str | None = Query(None, max_length=255),
    limit: int = Query(100, ge=1, le=MAX_PAGE_SIZE),
    offset: int = Query(0, ge=0),
    _auth: dict = Depends(verify_api_key),
):
    """The tracks at a tempo (`bpm` +- `tol`) or in a range (`bpm_from`..`bpm_to`), paged."""
    low, high, center, tolerance = resolve_window(bpm, tol, bpm_from, bpm_to)
    chosen = index_cache.get().select(low, high, min_confidence=min_confidence, genre=genre, center=center)
    page = chosen[offset : offset + limit]
    details = _details([e.track_id for e in page])
    tracks = [_track_view(e, details[e.track_id]) for e in page if e.track_id in details]
    next_offset = offset + limit if offset + limit < len(chosen) else None
    return {
        'bpm_from': low,
        'bpm_to': high,
        'center': center,
        'tolerance': tolerance,
        'min_confidence': min_confidence,
        'genre': genre or None,
        'total': len(chosen),
        'offset': offset,
        'next_offset': next_offset,
        'tracks': tracks,
    }


@router.get('/histogram')
def bpm_histogram(
    min_confidence: Confidence = 'low',
    genre: str | None = Query(None, max_length=255),
    bpm_from: float = Query(60.0, ge=BPM_MIN, le=BPM_MAX),
    bpm_to: float = Query(300.0, ge=BPM_MIN, le=BPM_MAX),
    _auth: dict = Depends(verify_api_key),
):
    """Tracks per whole BPM, the genres to filter on, and the defaults the page starts from."""
    index = index_cache.get()
    return {
        'bins': index.histogram(min_confidence=min_confidence, genre=genre, low=bpm_from, high=bpm_to),
        'genres': index.genre_counts(min_confidence=min_confidence),
        'default_tolerance': default_tolerance(),
        'summary': index.summary(),
    }


# ----------------------------------------------------------------------------- manual override

#: The permission the override needs; seeded for the admin role (rbac.PERMISSIONS).
OVERRIDE_PERMISSION = 'bpm.override'

TRACK_UID_SQL = 'SELECT track_uid FROM library_tracks WHERE id = %s'
#: One track's effective-BPM inputs (effective.resolve_row), and its measurement for the answer.
TRACK_INPUTS_SQL = INPUTS_SQL.format(where='\n      AND t.id = %s')
MEASURED_SQL = "SELECT bpm, raw_bpm FROM library_track_bpm WHERE track_uid = %s AND status = 'ok'"
SET_MANUAL_SQL = """
    INSERT INTO library_track_bpm_manual (track_uid, bpm, set_by, set_at)
    VALUES (%s, %s, %s, %s)
    ON DUPLICATE KEY UPDATE bpm = VALUES(bpm), set_by = VALUES(set_by), set_at = VALUES(set_at)
"""
CLEAR_MANUAL_SQL = 'DELETE FROM library_track_bpm_manual WHERE track_uid = %s'


class ManualBpm(BaseModel):
    """A tempo set by hand: `bpm` itself, or a `factor` (0.5 or 2) on the tempo shown now."""

    bpm: float | None = None
    # pydantic validates a float Literal; PEP 586 does not allow one, so mypy objects.
    factor: Literal[0.5, 2.0] | None = None  # type: ignore[valid-type]


def _track_uid(cursor, track_id: int) -> str:
    """The track's track_uid; 404 when there is no such track (or it has none)."""
    cursor.execute(TRACK_UID_SQL, (track_id,))
    row = cursor.fetchone()
    if not row or not row.get('track_uid'):
        raise HTTPException(status_code=404, detail='track not found')
    return str(row['track_uid'])


def _bpm_answer(cursor, track_id: int, track_uid: str) -> dict:
    """The track's effective BPM as the details show it, plus its measurement."""
    cursor.execute(TRACK_INPUTS_SQL, (track_id,))
    row = cursor.fetchone()
    found = resolve_row(row, reliable_confidence()) if row else None
    cursor.execute(MEASURED_SQL, (track_uid,))
    measured = cursor.fetchone() or {}
    return {
        'track_id': track_id,
        'bpm': found.bpm if found else None,
        'bpm_source': found.source if found else None,
        'bpm_confidence': found.confidence if found else None,
        'bpm_folded': found.folded if found else None,
        'bpm_approximate': found.approximate if found else None,
        'measured_bpm': float(measured['bpm']) if measured.get('bpm') is not None else None,
        'raw_bpm': float(measured['raw_bpm']) if measured.get('raw_bpm') is not None else None,
    }


def _after_change(track_id: int) -> None:
    """Bring the materialised table and the browse index along for one changed track."""
    try:
        effective_table.sync(get_db_connection, track_ids=[track_id], reliable_confidence=reliable_confidence())
    except Exception:  # pylint: disable=broad-except  # derived; the analyzer's next full sync repairs it
        logger.exception('bpm: syncing the effective BPM of track %s after a manual change failed', track_id)
    index_cache.mark_stale()


@router.put('/tracks/{track_id}/manual')
def set_manual_bpm(track_id: int, body: ManualBpm, auth: dict = Depends(rbac.require_permission(OVERRIDE_PERMISSION))):
    """Set a track's tempo by hand: a value, or half / double the tempo it shows now."""
    if (body.bpm is None) == (body.factor is None):
        raise HTTPException(status_code=400, detail='give either bpm or factor')
    conn = require_connection(get_db_connection())
    try:
        with conn.cursor() as cursor:
            track_uid = _track_uid(cursor, track_id)
            before = _bpm_answer(cursor, track_id, track_uid)
            if body.factor is not None:
                if before['bpm'] is None:
                    raise HTTPException(status_code=409, detail='the track has no BPM to halve or double')
                value = round(float(before['bpm']) * float(body.factor), 2)
            else:
                value = round(float(body.bpm), 2)  # type: ignore[arg-type]
            if not VALID_MIN <= value <= VALID_MAX:
                raise HTTPException(status_code=400, detail=f'a tempo must lie between {VALID_MIN:g} and {VALID_MAX:g}')
            actor_id = (auth.get('user') or {}).get('id')
            cursor.execute(SET_MANUAL_SQL, (track_uid, value, actor_id, datetime.now().replace(microsecond=0)))
            details = {
                'track_id': track_id,
                'bpm': value,
                'factor': body.factor,
                'previous_bpm': before['bpm'],
                'previous_source': before['bpm_source'],
            }
            rbac.record_audit_event(cursor, 'bpm.manual_set', actor_user_id=actor_id, details=json.dumps(details))
            conn.commit()
            after = _bpm_answer(cursor, track_id, track_uid)
    finally:
        conn.close()
    _after_change(track_id)
    return after


@router.delete('/tracks/{track_id}/manual')
def clear_manual_bpm(track_id: int, auth: dict = Depends(rbac.require_permission(OVERRIDE_PERMISSION))):
    """Forget a tempo set by hand: the track shows its measured (or tagged) tempo again."""
    conn = require_connection(get_db_connection())
    try:
        with conn.cursor() as cursor:
            track_uid = _track_uid(cursor, track_id)
            before = _bpm_answer(cursor, track_id, track_uid)
            cursor.execute(CLEAR_MANUAL_SQL, (track_uid,))
            if before['bpm_source'] == 'manual':
                actor_id = (auth.get('user') or {}).get('id')
                details = {'track_id': track_id, 'previous_bpm': before['bpm']}
                rbac.record_audit_event(
                    cursor, 'bpm.manual_cleared', actor_user_id=actor_id, details=json.dumps(details)
                )
            conn.commit()
            after = _bpm_answer(cursor, track_id, track_uid)
    finally:
        conn.close()
    _after_change(track_id)
    return after
