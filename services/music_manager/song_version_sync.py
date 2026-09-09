"""Push what muma decided about song versions into the server's own database.

muma owns the model: it has the label provenance and the download archives that decide
which version of a song wins, and LMS has neither. So LMS gets four columns on `track`
(migration 118) and muma fills them here, in the same lms.db pass that already syncs
users, playlists and artist images. No endpoint, no API key, no HTTP in the browsing
path -- see the design note in docs/superpowers/specs/2026-08-23-song-versions-and-canonical-design.md.

**The bridge is the file path**, because the two id spaces are unrelated: an LMS track id
and a muma track id have nothing to do with each other. LMS stores an absolute path in
`track.absolute_file_path`, muma stores its own under the mount it scans, and
`library_paths.candidate_paths()` already knows every spelling worth trying -- it is what
mirrored ratings use. Reusing it rather than writing a second matcher is deliberate: two
copies of that rule drifting apart is exactly how ratings once ended up keyed on a dead id.

**Everything unknown stays visible.** A track muma has not grouped yet -- roughly half the
library at any moment, while the worker works through its backlog -- keeps `is_canonical`
at 1 and gets a NULL `work_id`. The same holds for a path that does not match. A filter
built on this must fail towards showing a file twice, never towards hiding music that
exists, and that only holds if the sync actively *clears* a stale row rather than leaving
whatever it wrote last time: a track that left its work after a split would otherwise stay
hidden forever.

Written in one transaction per database, in chunks, against a database the server has open.
An UPDATE of four columns keyed on an indexed path is a different class of operation from
the DROP TABLE that once took production down (docs/bug-reports/005), but the same care
applies: short statements, no schema changes, and a busy timeout so a locked database is a
skipped sync instead of a failed one.
"""

import logging
import sqlite3

from services.music_manager.library_paths import candidate_paths

logger = logging.getLogger(__name__)

#: How many tracks to read from muma at a time. The join is cheap; the point of the chunk
#: is to keep each write transaction against the live server database short.
CHUNK = 2000

#: What muma knows about every track that has a media file, canonical or not. `is_canonical`
#: is computed rather than stored: the work names its winner, so a track is canonical when
#: the work points at it -- and a track without a work is canonical by default, which is
#: what keeps ungrouped music visible.
_TRACKS = """
    SELECT mf.file_path,
           t.work_id,
           COALESCE(t.version_kind, '') AS version_kind,
           COALESCE(t.version_score, 0) AS version_score,
           CASE
               WHEN t.work_id IS NULL THEN 1
               WHEN w.canonical_track_id IS NULL THEN 1
               WHEN w.canonical_track_id = t.id THEN 1
               ELSE 0
           END AS is_canonical
    FROM library_media_files mf
    JOIN library_tracks t ON t.id = mf.track_id
    LEFT JOIN library_works w ON w.id = t.work_id
    WHERE mf.file_path IS NOT NULL
"""

_UPDATE = """
    UPDATE track
    SET work_id = ?, is_canonical = ?, version_kind = ?, version_score = ?
    WHERE absolute_file_path = ?
"""


def _server_has_columns(server_cursor) -> bool:
    """Whether this server database has been through migration 118 yet.

    A deploy updates the images and the server migrates itself on startup, so a sync can
    land in the gap. Answering "not yet" and doing nothing is the whole handling: the next
    pass finds the columns.
    """
    server_cursor.execute('PRAGMA table_info(track)')
    columns = {row[1] for row in server_cursor.fetchall()}
    return {'work_id', 'is_canonical', 'version_kind', 'version_score'} <= columns


def sync_song_versions_to_server(muma_conn, server_conn) -> dict:
    """Write muma's version model into the server database. Returns what it did."""
    stats = {'considered': 0, 'matched': 0, 'skipped_no_columns': 0}
    server_cursor = server_conn.cursor()
    if not _server_has_columns(server_cursor):
        logger.info('Server database has no version columns yet; skipping the song-version sync')
        stats['skipped_no_columns'] = 1
        return stats

    try:
        server_conn.execute('PRAGMA busy_timeout = 5000')
        with muma_conn.cursor() as muma_cursor:
            muma_cursor.execute(_TRACKS)
            while True:
                rows = muma_cursor.fetchmany(CHUNK)
                if not rows:
                    break
                matched = 0
                for row in rows:
                    stats['considered'] += 1
                    # Every spelling of the path, because muma scans /mnt/music and the
                    # server was told /music. The first one that hits a row wins; a path
                    # that hits nothing is a file the server does not have, which is not
                    # an error -- the two libraries are allowed to differ.
                    for path in candidate_paths(row['file_path']):
                        server_cursor.execute(
                            _UPDATE,
                            (row['work_id'], row['is_canonical'], row['version_kind'], row['version_score'], path),
                        )
                        if server_cursor.rowcount:
                            matched += server_cursor.rowcount
                            break
                server_conn.commit()
                stats['matched'] += matched
    except sqlite3.OperationalError as e:
        # A locked database is the server doing its own work. Losing this pass costs
        # nothing: the next one writes the same rows.
        logger.warning('Song-version sync could not write to the server database: %s', e)
    except Exception as e:
        logger.error('Song-version sync failed: %s', e, exc_info=True)

    logger.info(
        'Song-version sync: %s tracks considered, %s matched in the server database',
        stats['considered'],
        stats['matched'],
    )
    return stats
