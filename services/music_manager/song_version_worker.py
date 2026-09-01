"""Grouping every track under a song, and choosing which one plays.

The rules live in song_versions.py; this module owns the SQL.

Deliberately a worker rather than a step in process_file(): tracks are inserted
from the scanner and the ml-analyzer today and from somewhere else tomorrow, and
a grouping that hangs off one writer misses the rest in silence. Same reasoning
as backfill_normalized() in scrobble_rematch.py.

Design: docs/superpowers/specs/2026-08-23-song-versions-and-canonical-design.md
"""

from __future__ import annotations

import os
import sys
import time

from services.music_manager.database import get_db_connection
from services.music_manager.song_versions import (
    derived_bitrate,
    version_kind,
    version_score,
    work_key,
)

BATCH_SIZE = int(os.getenv('SONG_VERSION_BATCH', '500'))
INTERVAL_SECONDS = int(os.getenv('SONG_VERSION_INTERVAL', '3600'))

# One row per track that still needs a work, carrying everything the ranking asks
# for. The label join decides provenance together with the two download archives:
# an official release has a label and was not downloaded from anywhere.
_UNGROUPED = '''
    SELECT
        t.id,
        t.title,
        a.name AS artist,
        mf.file_path,
        mf.file_size,
        COALESCE(mf.duration_secs, t.duration_secs) AS duration_secs,
        EXISTS (SELECT 1 FROM library_track_labels tl WHERE tl.track_id = t.id) AS has_label,
        EXISTS (
            SELECT 1 FROM downloads_soundcloud_archive sc
            WHERE sc.filename = SUBSTRING_INDEX(mf.file_path, '/', -1)
        ) AS from_soundcloud,
        EXISTS (
            SELECT 1 FROM downloads_youtube_archive yt
            WHERE yt.filename = SUBSTRING_INDEX(mf.file_path, '/', -1)
        ) AS from_youtube
    FROM library_tracks t
    LEFT JOIN library_artists a ON a.id = t.primary_artist_id
    LEFT JOIN library_media_files mf ON mf.track_id = t.id
    WHERE t.work_id IS NULL AND t.work_locked = 0
    ORDER BY t.id
    LIMIT %s
'''

# Highest score wins; the two tie-breaks keep the choice stable between passes so
# the canonical does not move on its own.
_BEST_TRACK = '''
    SELECT t.id
    FROM library_tracks t
    LEFT JOIN library_media_files mf ON mf.track_id = t.id
    WHERE t.work_id = %s
    ORDER BY t.version_score DESC,
             (mf.file_size / NULLIF(mf.duration_secs, 0)) DESC,
             t.created_at ASC,
             t.id ASC
    LIMIT 1
'''


def _rank_row(row) -> tuple[str, int]:
    """The kind and packed score for one candidate row."""
    kind = version_kind(row['title'])
    is_official = bool(row['has_label']) and not (row['from_soundcloud'] or row['from_youtube'])
    bitrate = derived_bitrate(row['file_size'], row['duration_secs'])
    return kind, version_score(is_official, kind, row['file_path'] or '', bitrate)


def _best_per_track(rows) -> dict[int, dict]:
    """One entry per track, scored on its best file.

    A track can own several files -- the FLAC and the MP3 of one release -- so the
    join returns it once per file. The spec ranks a track on its best one, and
    without this the last row seen would win instead of the best.
    """
    best: dict[int, dict] = {}
    for row in rows:
        kind, score = _rank_row(row)
        current = best.get(row['id'])
        if current is None or score > current['score']:
            best[row['id']] = {'row': row, 'kind': kind, 'score': score}
    return best


def assign_works(cursor, limit: int = BATCH_SIZE) -> tuple[set[int], int]:
    """Give every ungrouped track a work, a kind and a score.

    Returns the work ids that were touched and how many tracks were assigned. The
    limit counts joined rows rather than tracks, so a batch can cover slightly
    fewer tracks than asked; the next pass picks up the remainder.
    """
    cursor.execute(_UNGROUPED, (limit,))
    rows = cursor.fetchall()

    touched: set[int] = set()
    candidates = _best_per_track(rows)
    for track_id, candidate in candidates.items():
        row = candidate['row']
        key = work_key(row['artist'], row['title'])
        cursor.execute(
            'INSERT INTO library_works (work_key, title, primary_artist_id) '
            'VALUES (%s, %s, (SELECT primary_artist_id FROM library_tracks WHERE id = %s)) '
            'ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)',
            (key, row['title'], track_id),
        )
        cursor.execute('SELECT id FROM library_works WHERE work_key = %s', (key,))
        work_id = cursor.fetchone()['id']

        cursor.execute(
            'UPDATE library_tracks SET work_id = %s, version_kind = %s, version_score = %s WHERE id = %s',
            (work_id, candidate['kind'], candidate['score'], track_id),
        )
        touched.add(work_id)

    return touched, len(candidates)


def recompute_canonicals(cursor, work_ids: set[int]) -> int:
    """Set canonical_track_id for each work. A pin wins; otherwise the best score does."""
    for work_id in work_ids:
        cursor.execute('SELECT pinned_track_id FROM library_works WHERE id = %s', (work_id,))
        row = cursor.fetchone()
        if row is None:
            continue

        canonical = row['pinned_track_id']
        if canonical is None:
            cursor.execute(_BEST_TRACK, (work_id,))
            best = cursor.fetchone()
            canonical = best['id'] if best else None

        cursor.execute(
            'UPDATE library_works SET canonical_track_id = %s WHERE id = %s',
            (canonical, work_id),
        )
    return len(work_ids)


def group_once(conn) -> dict:
    """One pass. Idempotent: a second call over unchanged data writes nothing new."""
    with conn.cursor() as cursor:
        touched, assigned = assign_works(cursor)

        # Works whose pin moved need recomputing even when no track was assigned.
        cursor.execute(
            'SELECT id FROM library_works '
            'WHERE pinned_track_id IS NOT NULL AND pinned_track_id <> COALESCE(canonical_track_id, 0)'
        )
        touched.update(row['id'] for row in cursor.fetchall())

        recomputed = recompute_canonicals(cursor, touched)

        cursor.execute('SELECT COUNT(*) AS n FROM library_tracks WHERE work_id IS NULL AND work_locked = 0')
        remaining = cursor.fetchone()['n']
    conn.commit()
    return {'assigned': assigned, 'remaining': remaining, 'recomputed': recomputed}


def run_song_version_grouping() -> None:
    while True:
        try:
            conn = get_db_connection()
            if conn:
                try:
                    stats = group_once(conn)
                    if stats['recomputed']:
                        print(f"song-versions: recomputed {stats['recomputed']} works")
                finally:
                    conn.close()
        except Exception as exc:
            print(f'song-versions: pass failed: {exc}', file=sys.stderr)
        time.sleep(INTERVAL_SECONDS)
