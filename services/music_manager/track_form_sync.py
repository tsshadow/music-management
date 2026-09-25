"""Settle every track's form and performance date, and hand both to the servers.

Two passes, both run by `routers/users.run_lms_db_sync` every hour:

1. **`classify_library`** recomputes `library_tracks.form` and `performance_date` for the whole
   library with `services.common.track_form.classify` -- the function the scanner calls for the
   one file it reads -- and writes only the rows that changed. This is the backfill: the first
   pass after the deploy that adds the columns writes the library in 5,000-row windows, and every
   later pass writes only what a curation decision changed (a festival alias, an edition date, an
   approved show). No file is read and none is written, so the tagger queue is not involved and
   the deploy runs no data migration (migrate_v42_track_form.sql adds columns only).

2. **`push_forms_to_server`** writes both values into each server's `track` table (LMS migration
   step 122), so `getSpotifyTracks` and `getSongs` can filter on them. Same shape as the
   song-version push and deliberately reusing its lock handling: read every row without a
   transaction, keep the ones the server disagrees with, write those in batches short enough that
   the player never waits on them. See song_version_sync's module docstring for why.

The two id spaces are bridged by the file path, as everywhere else (`library_paths`).
"""

import logging
import time

from services.common.track_form import classify
from services.music_manager.library_paths import candidate_paths
from services.music_manager.song_version_sync import BUSY_TIMEOUT_STATEMENT, CHUNK, WRITE_BATCH, _write_batch

logger = logging.getLogger(__name__)

#: How many track ids one classification window covers -- the release-date sync's window.
ID_WINDOW = 5000

#: One row per track. A track with several files (the FLAC and the MP3 of one release) is judged
#: by its lexically first path; the forms of two copies of one recording only differ when they
#: sit in different top folders, which is a filing mistake rather than two answers.
_MUMA_TRACKS = """
    SELECT t.id, t.title, t.duration_secs, t.form, t.performance_date, MIN(mf.file_path) AS file_path
    FROM library_tracks t
    LEFT JOIN library_media_files mf ON mf.track_id = t.id
    WHERE t.id >= %s AND t.id < %s
    GROUP BY t.id, t.title, t.duration_secs, t.form, t.performance_date
"""

_UPDATE_MUMA = 'UPDATE library_tracks SET form = %s, performance_date = %s WHERE id = %s'

#: What muma knows per file for the server push. The empty string is the server's "not said".
_MUMA_FILES = """
    SELECT mf.file_path, COALESCE(t.form, '') AS form, COALESCE(t.performance_date, '') AS performance_date
    FROM library_media_files mf
    JOIN library_tracks t ON t.id = mf.track_id
    WHERE mf.file_path IS NOT NULL
"""

_SERVER_CURRENT = 'SELECT form, performance_date FROM track WHERE absolute_file_path = ? LIMIT 1'

_SERVER_UPDATE = 'UPDATE track SET form = ?, performance_date = ? WHERE absolute_file_path = ?'


def _windows(cursor) -> range:
    cursor.execute('SELECT MIN(id) AS low, MAX(id) AS high FROM library_tracks')
    bounds = cursor.fetchone() or {}
    low, high = bounds.get('low'), bounds.get('high')
    if low is None:
        return range(0)
    return range(low, high + 1, ID_WINDOW)


def _changes(rows, music_root, festivals, podcasts) -> list[tuple]:
    """`(form, performance_date, id)` for every row whose stored pair differs from the derived one."""
    updates = []
    for row in rows:
        form, performance_date = classify(
            row['file_path'], music_root, row['duration_secs'], row['title'], festivals, podcasts
        )
        if (form, performance_date) != (row['form'], row['performance_date']):
            updates.append((form, performance_date, row['id']))
    return updates


def classify_library(muma_conn, music_root: str, festivals, podcasts) -> dict:
    """Recompute form and performance date for every track; write the difference. Returns counts."""
    stats = {'considered': 0, 'written': 0}
    started = time.monotonic()
    try:
        with muma_conn.cursor() as cursor:
            for low in _windows(cursor):
                cursor.execute(_MUMA_TRACKS, (low, low + ID_WINDOW))
                rows = cursor.fetchall()
                stats['considered'] += len(rows)
                updates = _changes(rows, music_root, festivals, podcasts)
                if not updates:
                    continue
                cursor.executemany(_UPDATE_MUMA, updates)
                muma_conn.commit()
                stats['written'] += len(updates)
    except Exception as e:
        logger.error('track-form pass failed: %s', e, exc_info=True)
    # The duration is logged because it is the number that says whether an hourly cadence still
    # fits: every long title is matched against every festival and show alias.
    logger.info(
        'track-form pass considered %s tracks, wrote %s in %.1fs',
        stats['considered'],
        stats['written'],
        time.monotonic() - started,
    )
    return stats


def _server_has_columns(server_cursor) -> bool:
    """Whether this server database has been through LMS migration step 122 yet."""
    server_cursor.execute('PRAGMA table_info(track)')
    columns = {row[1] for row in server_cursor.fetchall()}
    return {'form', 'performance_date'} <= columns


def _rows_to_write(server_cursor, rows) -> list[tuple]:
    """Which rows the server disagrees with, as `((form, performance_date), path)` pairs."""
    pending = []
    for row in rows:
        values = (row['form'] or '', row['performance_date'] or '')
        for path in candidate_paths(row['file_path']):
            server_cursor.execute(_SERVER_CURRENT, (path,))
            current = server_cursor.fetchone()
            if current is None:
                continue
            if (current[0] or '', current[1] or '') != values:
                pending.append((values, path))
            break
    return pending


def push_forms_to_server(muma_conn, server_conn, source: str = 'unknown') -> dict:
    """Write form and performance date into one server database. Returns counts."""
    stats = {'considered': 0, 'matched': 0, 'skipped_no_columns': 0, 'chunks_skipped': 0}
    server_cursor = server_conn.cursor()
    if not _server_has_columns(server_cursor):
        logger.info('%s: no form columns yet, skipping the track-form push', source)
        stats['skipped_no_columns'] = 1
        return stats
    try:
        server_conn.execute(BUSY_TIMEOUT_STATEMENT)
        with muma_conn.cursor() as muma_cursor:
            muma_cursor.execute(_MUMA_FILES)
            while True:
                rows = muma_cursor.fetchmany(CHUNK)
                if not rows:
                    break
                stats['considered'] += len(rows)
                pending = _rows_to_write(server_cursor, rows)
                for start in range(0, len(pending), WRITE_BATCH):
                    stats['matched'] += _write_batch(
                        server_conn,
                        server_cursor,
                        pending[start : start + WRITE_BATCH],
                        stats,
                        source,
                        update_sql=_SERVER_UPDATE,
                    )
    except Exception as e:
        logger.error('%s: track-form push failed: %s', source, e, exc_info=True)
    logger.info('%s: track-form push considered %s files, wrote %s', source, stats['considered'], stats['matched'])
    return stats


def run_classification(muma_conn) -> dict:
    """`classify_library` with the rules as they stand now: the production entry point."""
    from services.common.config_store import ConfigStore
    from services.common.Helpers.FestivalHelper import FestivalHelper
    from services.common.Helpers.PodcastHelper import PodcastHelper

    return classify_library(muma_conn, ConfigStore().music_folder_path, FestivalHelper(), PodcastHelper())
