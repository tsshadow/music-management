"""Reading a song's versions, and the two ways of correcting the grouping by hand.

The pin decides which version wins. The split decides whether two tracks belong
together at all -- without it a wrong merge can only be repaired by editing tags,
and a wrong merge is silent.

Design: docs/superpowers/specs/2026-08-23-song-versions-and-canonical-design.md
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from services.music_manager.database import get_db_connection, require_connection, transaction
from services.music_manager.deprecation import DEPRECATED_CALL
from services.music_manager.routers.users import verify_api_key
from services.music_manager.song_version_worker import recompute_canonicals
from services.music_manager.song_versions import SPLIT_PREFIX

router = APIRouter(tags=['songs'])

_VERSIONS = '''
    SELECT t.id AS track_id, t.title, t.version_kind, t.version_score,
           w.canonical_track_id,
           mf.file_path
    FROM library_tracks t
    JOIN library_works w ON w.id = t.work_id
    LEFT JOIN library_media_files mf ON mf.track_id = t.id
    WHERE t.work_id = %s
    ORDER BY t.version_score DESC, t.id ASC
'''


class Pin(BaseModel):
    track_id: int | None = None


def _connection():
    """A pooled connection; no pool at all is a 503 (database.require_connection)."""
    return require_connection(get_db_connection())


@router.get('/{work_id}')
def get_song(work_id: int, _auth: dict = Depends(verify_api_key)):
    conn = _connection()
    try:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id, title, work_key, canonical_track_id, pinned_track_id FROM library_works WHERE id = %s',
                (work_id,),
            )
            work = cursor.fetchone()
            if not work:
                raise HTTPException(status_code=404, detail='No such song')

            cursor.execute(_VERSIONS, (work_id,))
            versions = [
                {
                    'track_id': row['track_id'],
                    'title': row['title'],
                    'version_kind': row['version_kind'],
                    'version_score': row['version_score'],
                    'file_path': row['file_path'],
                    'is_canonical': row['track_id'] == row['canonical_track_id'],
                }
                for row in cursor.fetchall()
            ]
    finally:
        conn.close()

    return {
        'work_id': work['id'],
        'title': work['title'],
        'pinned_track_id': work['pinned_track_id'],
        'versions': versions,
    }


@router.post('/{work_id}/pin')
def pin_version(work_id: int, pin: Pin, _auth: dict = Depends(verify_api_key)):
    """Pin a version, or clear the pin by sending a null track_id."""
    conn = _connection()
    try:
        with transaction(conn), conn.cursor() as cursor:
            if pin.track_id is not None:
                cursor.execute('SELECT work_id FROM library_tracks WHERE id = %s', (pin.track_id,))
                row = cursor.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail='No such track')
                if row['work_id'] != work_id:
                    raise HTTPException(status_code=400, detail='That track belongs to a different song')

            cursor.execute('UPDATE library_works SET pinned_track_id = %s WHERE id = %s', (pin.track_id, work_id))
            recompute_canonicals(cursor, {work_id})
    finally:
        conn.close()
    return {'status': 'ok', 'work_id': work_id, 'pinned_track_id': pin.track_id}


@router.post('/tracks/{track_id}/split', deprecated=True, dependencies=[DEPRECATED_CALL])
def split_track(track_id: int, _auth: dict = Depends(verify_api_key)):
    """Pull a track out of its group, give it a work of its own, and lock it there.

    The lock is what makes it stick: without it the next grouping pass would
    recompute the same key and put the track straight back.
    """
    conn = _connection()
    try:
        with transaction(conn), conn.cursor() as cursor:
            cursor.execute('SELECT work_id, title, primary_artist_id FROM library_tracks WHERE id = %s', (track_id,))
            track = cursor.fetchone()
            if track is None:
                raise HTTPException(status_code=404, detail='No such track')

            old_work_id = track['work_id']
            # The key is suffixed with the track id so it cannot collide with the
            # group it was just taken out of, nor with a later split of another track.
            cursor.execute(
                'INSERT INTO library_works (work_key, title, primary_artist_id) VALUES (%s, %s, %s)',
                (f'{SPLIT_PREFIX}{track_id}', track['title'], track['primary_artist_id']),
            )
            new_work_id = cursor.lastrowid

            cursor.execute(
                'UPDATE library_tracks SET work_id = %s, work_locked = 1 WHERE id = %s',
                (new_work_id, track_id),
            )

            to_recompute = {new_work_id}
            if old_work_id:
                # The track it names has just left, so the pin no longer decides
                # anything here. Left in place it would keep the old work's canonical
                # pointing at a track that is now a song of its own.
                cursor.execute(
                    'UPDATE library_works SET pinned_track_id = NULL WHERE id = %s AND pinned_track_id = %s',
                    (old_work_id, track_id),
                )
                to_recompute.add(old_work_id)
            recompute_canonicals(cursor, to_recompute)
    finally:
        conn.close()
    return {'status': 'ok', 'track_id': track_id, 'work_id': new_work_id}
