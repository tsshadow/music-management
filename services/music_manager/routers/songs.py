"""Reading a song's versions, and the ways of correcting the choice by hand.

The pin decides which version wins. The split decides whether two tracks belong
together at all -- without it a wrong merge can only be repaired by editing tags,
and a wrong merge is silent.

The curation list (`GET /api/songs/curation`) feeds the Versions page in Management: every
song with more than one version, the automatic choice, and a flag on the songs whose
choice a rescore changed. Reads need an API key, every write needs `rules.manage`.

Design: docs/designs/song-versions/technical.md and, for
the ranking, the rescore and the Versions page, docs/designs/song-versions/.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from services.music_manager.database import get_db_connection, require_connection, transaction
from services.music_manager.rbac import require_permission
from services.music_manager.routers.users import verify_api_key
from services.music_manager.song_version_worker import ranking_context, recompute_canonicals
from services.music_manager.song_versions import (
    derived_bitrate,
    file_extension,
    is_official_release,
)

router = APIRouter(tags=['songs'])

WRITE = Depends(require_permission('rules.manage'))

PAGE_SIZE_MAX = 100

# One row per file of every member. Rating and plays are per track: the highest rating any
# user gave it (ratings key on track_uid, see routers/rating.py) and the matched listens.
_VERSIONS = '''
    SELECT t.id AS track_id, t.title, t.version_kind, t.version_score,
           w.canonical_track_id,
           mf.file_path, mf.file_size,
           COALESCE(mf.duration_secs, t.duration_secs) AS duration_secs,
           EXISTS (SELECT 1 FROM library_track_labels tl WHERE tl.track_id = t.id) AS has_label,
           EXISTS (SELECT 1 FROM downloads_soundcloud_archive sc WHERE sc.filename = mf.file_path)
               AS from_soundcloud,
           EXISTS (SELECT 1 FROM downloads_youtube_archive yt WHERE yt.path = mf.file_path)
               AS from_youtube,
           (SELECT MAX(r.rating) FROM rating_tracks r
             WHERE r.entity_type = 'track' AND r.entity_id = t.track_uid) AS rating,
           (SELECT COUNT(*) FROM scrobble_listens sl WHERE sl.track_id = t.id) AS plays
    FROM library_tracks t
    JOIN library_works w ON w.id = t.work_id
    LEFT JOIN library_media_files mf ON mf.track_id = t.id
    WHERE t.work_id = %s
    ORDER BY t.version_score DESC, t.id ASC
'''

# Works with more than one member. The count is taken in a derived table so the filter and
# the paging apply to works, not to their tracks. The two statements share their FROM, spelled
# out twice on purpose: each is one literal, so nothing is ever concatenated into SQL. The sort
# is a bound parameter chosen from a Literal and read by CASE, not text in the statement.
_CURATION_COUNT = '''
    SELECT COUNT(*) AS n
    FROM (
        SELECT work_id FROM library_tracks
        WHERE work_id IS NOT NULL
        GROUP BY work_id
        HAVING COUNT(*) > 1
    ) AS counted
    JOIN library_works w ON w.id = counted.work_id
    LEFT JOIN library_artists a ON a.id = w.primary_artist_id
    WHERE (%s = '' OR w.title LIKE %s OR a.name LIKE %s)
      AND (%s = 0 OR w.canonical_changed_at IS NOT NULL)
'''

_CURATION_PAGE = '''
    SELECT w.id, w.title, a.name AS artist, counted.version_count, w.canonical_track_id,
           ct.title AS canonical_title, w.pinned_track_id, w.previous_canonical_track_id,
           w.canonical_changed_at
    FROM (
        SELECT work_id, COUNT(*) AS version_count
        FROM library_tracks
        WHERE work_id IS NOT NULL
        GROUP BY work_id
        HAVING COUNT(*) > 1
    ) AS counted
    JOIN library_works w ON w.id = counted.work_id
    LEFT JOIN library_artists a ON a.id = w.primary_artist_id
    LEFT JOIN library_tracks ct ON ct.id = w.canonical_track_id
    WHERE (%s = '' OR w.title LIKE %s OR a.name LIKE %s)
      AND (%s = 0 OR w.canonical_changed_at IS NOT NULL)
    ORDER BY
        CASE WHEN %s = 'versions' THEN counted.version_count END DESC,
        CASE WHEN %s = 'changed' THEN w.canonical_changed_at IS NULL END ASC,
        CASE WHEN %s = 'changed' THEN w.canonical_changed_at END DESC,
        CASE WHEN %s = 'title' THEN w.title END ASC,
        w.id ASC
    LIMIT %s OFFSET %s
'''


class Pin(BaseModel):
    """The version to pin; null hands the choice back to the ranking."""

    track_id: int | None = None


def _connection():
    """A pooled connection; no pool at all is a 503 (database.require_connection)."""
    return require_connection(get_db_connection())


def _iso(value):
    """A timestamp as ISO text, None as None."""
    return value.isoformat() if hasattr(value, 'isoformat') else value


def _source(row, official: bool) -> str:
    """Where a file came from, as the Versions page labels it."""
    if row.get('from_soundcloud'):
        return 'soundcloud'
    if row.get('from_youtube'):
        return 'youtube'
    if official:
        return 'label'
    return 'other'


@router.get('/curation')
def list_curation(
    q: str = '',
    sort: Literal['versions', 'changed', 'title'] = 'versions',
    changed_only: bool = False,
    page: int = Query(1, ge=1),
    page_size: int = Query(50, ge=1, le=PAGE_SIZE_MAX),
    _auth: dict = Depends(verify_api_key),
):
    """Every song with more than one version, paged, for the Versions page."""
    needle = q.strip()
    like = f'%{needle}%'
    filters = (needle, like, like, 1 if changed_only else 0)
    conn = _connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(_CURATION_COUNT, filters)
            total = (cursor.fetchone() or {}).get('n', 0)
            cursor.execute(_CURATION_PAGE, (*filters, sort, sort, sort, sort, page_size, (page - 1) * page_size))
            rows = cursor.fetchall()
    finally:
        conn.close()

    return {
        'items': [
            {
                'work_id': row['id'],
                'title': row['title'],
                'artist': row['artist'],
                'version_count': row['version_count'],
                'canonical_track_id': row['canonical_track_id'],
                'canonical_title': row['canonical_title'],
                'pinned_track_id': row['pinned_track_id'],
                'previous_canonical_track_id': row['previous_canonical_track_id'],
                'canonical_changed_at': _iso(row['canonical_changed_at']),
            }
            for row in rows
        ],
        'total': total,
        'page': page,
        'page_size': page_size,
    }


@router.get('/ranking')
def ranking_status(_auth: dict = Depends(verify_api_key)):
    """The ranking in force, how many songs still await its rescore, and how many it changed."""
    context = ranking_context()
    conn = _connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT '
                'SUM(ranking_signature IS NULL OR ranking_signature <> %s) AS pending, '
                'SUM(canonical_changed_at IS NOT NULL) AS changed '
                'FROM library_works',
                (context.signature,),
            )
            row = cursor.fetchone() or {}
    finally:
        conn.close()
    return {
        'signature': context.signature,
        'prefer_lossless': context.prefer_lossless,
        'pending_works': int(row.get('pending') or 0),
        'changed_works': int(row.get('changed') or 0),
    }


@router.get('/{work_id}')
def get_song(work_id: int, _auth: dict = Depends(verify_api_key)):
    """One song with every version: kind, format, bitrate, source, rating and plays."""
    context = ranking_context()
    conn = _connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT w.id, w.title, w.work_key, w.canonical_track_id, w.pinned_track_id, '
                'w.previous_canonical_track_id, w.canonical_changed_at, a.name AS artist '
                'FROM library_works w LEFT JOIN library_artists a ON a.id = w.primary_artist_id '
                'WHERE w.id = %s',
                (work_id,),
            )
            work = cursor.fetchone()
            if not work:
                raise HTTPException(status_code=404, detail='No such song')

            cursor.execute(_VERSIONS, (work_id,))
            versions = []
            for row in cursor.fetchall():
                official = is_official_release(
                    row.get('file_path'),
                    bool(row.get('has_label')),
                    bool(row.get('from_soundcloud') or row.get('from_youtube')),
                    context.label_tree_roots,
                )
                versions.append(
                    {
                        'track_id': row['track_id'],
                        'title': row['title'],
                        'version_kind': row['version_kind'],
                        'version_score': row['version_score'],
                        'file_path': row['file_path'],
                        'format': file_extension(row.get('file_path')) or None,
                        'bitrate_kbps': derived_bitrate(row.get('file_size'), row.get('duration_secs')) or None,
                        'duration_secs': row.get('duration_secs'),
                        'source': _source(row, official) if row.get('file_path') else None,
                        'is_official': official,
                        'rating': row.get('rating'),
                        'plays': int(row.get('plays') or 0),
                        'is_canonical': row['track_id'] == row['canonical_track_id'],
                    }
                )
    finally:
        conn.close()

    return {
        'work_id': work['id'],
        'title': work['title'],
        'artist': work.get('artist'),
        'canonical_track_id': work.get('canonical_track_id'),
        'pinned_track_id': work['pinned_track_id'],
        'previous_canonical_track_id': work.get('previous_canonical_track_id'),
        'canonical_changed_at': _iso(work.get('canonical_changed_at')),
        'versions': versions,
    }


@router.post('/{work_id}/pin')
def pin_version(work_id: int, pin: Pin, _auth: dict = WRITE):
    """Pin a version, or hand the choice back to the ranking by sending a null track_id.

    Either way the song has been looked at, so a "changed by the rescore" flag on it is
    cleared along with the old choice it remembered.
    """
    conn = _connection()
    try:
        with transaction(conn), conn.cursor() as cursor:
            cursor.execute('SELECT id FROM library_works WHERE id = %s', (work_id,))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail='No such song')
            if pin.track_id is not None:
                cursor.execute('SELECT work_id FROM library_tracks WHERE id = %s', (pin.track_id,))
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail='No such track')
                if row['work_id'] != work_id:
                    raise HTTPException(status_code=400, detail='That track belongs to a different song')

            cursor.execute(
                'UPDATE library_works SET pinned_track_id = %s, previous_canonical_track_id = NULL, '
                'canonical_changed_at = NULL WHERE id = %s',
                (pin.track_id, work_id),
            )
            recompute_canonicals(cursor, {work_id})
    finally:
        conn.close()
    return {'status': 'ok', 'work_id': work_id, 'pinned_track_id': pin.track_id}


@router.post('/{work_id}/dismiss-change')
def dismiss_change(work_id: int, _auth: dict = WRITE):
    """Accept what the rescore chose: clear the flag, keep the new canonical."""
    conn = _connection()
    try:
        with transaction(conn), conn.cursor() as cursor:
            cursor.execute('SELECT id FROM library_works WHERE id = %s', (work_id,))
            if cursor.fetchone() is None:
                raise HTTPException(status_code=404, detail='No such song')
            cursor.execute(
                'UPDATE library_works SET previous_canonical_track_id = NULL, canonical_changed_at = NULL '
                'WHERE id = %s',
                (work_id,),
            )
    finally:
        conn.close()
    return {'status': 'ok', 'work_id': work_id}
