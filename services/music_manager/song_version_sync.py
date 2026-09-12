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

Read first, write the difference. The server database is the player's, and the player
does not wait for it: a Dbo transaction reads before it writes, and SQLite answers a
read-to-write upgrade with SQLITE_BUSY the moment another connection holds the write lock
-- the busy timeout only applies to a connection with no transaction open. So while this
job held that lock, a rating from the app was a 500 and a scrobble was lost. This job
therefore reads every chunk without a transaction (reads take no write lock in WAL mode),
keeps only the rows the server disagrees with, and writes those in transactions short
enough to be gone before anyone notices. After the first pass almost nothing disagrees and
almost nothing is written. An UPDATE of four columns keyed on
an indexed path is a different class of operation from the DROP TABLE that once took
production down (docs/bug-reports/005), but the same care applies: short statements, no
schema changes, and a busy timeout so a locked database is a skipped batch instead of a
failed sync.
"""

import contextlib
import logging
import sqlite3
import time

from services.music_manager.library_paths import candidate_paths

logger = logging.getLogger(__name__)

#: How many tracks to read from muma at a time. The join is cheap; the chunk bounds how
#: much sits in memory, not how long a write transaction lasts -- WRITE_BATCH does that.
CHUNK = 2000

#: How long a statement waits for the server to let go of its write lock -- deliberately
#: short. This is a background job and LMS is the player: when the two want the same lock,
#: the one nobody is listening to has to yield. Thirty seconds did the opposite, and LMS
#: does not wait at all -- it dies on a locked database with an uncaught exception, which
#: cost 102 restarts and the whole library being unreachable.
#:
#: Spelled out as a literal statement rather than built from the number. PRAGMA takes no
#: bound parameter, so any computed form is a formatted SQL string -- a shape worth not
#: having at all here, rather than one to explain away in the security baseline.
#: SongVersionSyncTest keeps the two in step.
BUSY_TIMEOUT_MS = 2000
BUSY_TIMEOUT_STATEMENT = 'PRAGMA busy_timeout = 2000'

#: How often a chunk may find the database locked before the pass gives up on it. Few, and
#: far apart: retrying hard is what turned a busy server into a crashing one. What is left
#: undone costs nothing -- the next hourly pass writes the same rows.
LOCK_RETRIES = 3

#: How long to wait after a locked chunk before trying it again. Long enough for a scan
#: step to finish rather than to fight it.
LOCK_BACKOFF_SECONDS = 60

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

#: What the server currently says about this file. Read before anything is written, so a
#: row that already agrees costs a read and no write -- and, more to the point, no write
#: *transaction*. An UPDATE whose WHERE matches nothing still takes SQLite's write lock
#: from the moment it runs until the commit, and that is what the player ran into.
_CURRENT = 'SELECT work_id, is_canonical, version_kind, version_score FROM track WHERE absolute_file_path = ? LIMIT 1'

#: How many UPDATEs share one write transaction. The player aborts a request -- a rating,
#: a scrobble, a token bump -- the instant it meets this job's lock (see the module
#: docstring), so every transaction this job opens has to be a blink. A hundred indexed
#: UPDATEs commit in milliseconds; the first pass over the whole library is a few thousand
#: of those blinks rather than one ten-minute hold.
WRITE_BATCH = 100


def _server_has_columns(server_cursor) -> bool:
    """Whether this server database has been through migration 118 yet.

    A deploy updates the images and the server migrates itself on startup, so a sync can
    land in the gap. Answering "not yet" and doing nothing is the whole handling: the next
    pass finds the columns.
    """
    server_cursor.execute('PRAGMA table_info(track)')
    columns = {row[1] for row in server_cursor.fetchall()}
    return {'work_id', 'is_canonical', 'version_kind', 'version_score'} <= columns


def _as_stored(values) -> tuple:
    """The shape SQLite hands back, so a muma row and a server row compare as equals."""
    work_id, is_canonical, version_kind, version_score = values
    return (
        None if work_id is None else int(work_id),
        int(is_canonical),
        str(version_kind or ''),
        int(version_score or 0),
    )


def _rows_to_write(server_cursor, rows) -> list[tuple]:
    """Which rows of this chunk the server disagrees with, as (values, path) pairs.

    Pure reads, and reads take no write lock in WAL mode: the player is not in the way and
    this is not in the player's way. After the first pass almost every row agrees, so
    almost every chunk ends here with nothing to write.
    """
    pending = []
    for row in rows:
        values = _as_stored((row['work_id'], row['is_canonical'], row['version_kind'], row['version_score']))
        # Every spelling of the path, because muma scans /mnt/music and the server was told
        # /music. The first one the server knows wins; a path it knows nothing about is a
        # file it does not have, which is not an error -- the two libraries are allowed to
        # differ.
        for path in candidate_paths(row['file_path']):
            server_cursor.execute(_CURRENT, (path,))
            current = server_cursor.fetchone()
            if current is None:
                continue
            if _as_stored(current) != values:
                pending.append((values, path))
            break
    return pending


def _write_batch(server_conn, server_cursor, batch, stats: dict, source: str) -> int:
    """Write one batch, waiting out the server's write lock rather than giving up on it.

    A locked database is LMS doing its own work -- a scan step, a playlist write -- and it
    lets go again. The first version of this treated the lock as the end of the whole pass,
    which is how a deploy that restarted both services wrote one track out of 285.332 and
    left the columns a day stale. A batch that stays locked is skipped, not fatal: the next
    pass rewrites the same rows.
    """
    for attempt in range(1, LOCK_RETRIES + 1):
        matched = 0
        try:
            for values, path in batch:
                server_cursor.execute(_UPDATE, values + (path,))
                matched += server_cursor.rowcount
            server_conn.commit()
            return matched
        except sqlite3.OperationalError as e:
            if 'locked' not in str(e).lower() and 'busy' not in str(e).lower():
                raise
            with contextlib.suppress(Exception):
                server_conn.rollback()
            if attempt == LOCK_RETRIES:
                stats['chunks_skipped'] = stats.get('chunks_skipped', 0) + 1
                logger.warning('%s: gave up on a batch after %s locked attempts', source, attempt)
                return 0
            logger.info('%s: server database locked, waiting %ss', source, LOCK_BACKOFF_SECONDS)
            time.sleep(LOCK_BACKOFF_SECONDS)
    return 0


def _write_chunk(server_conn, server_cursor, rows, stats: dict, source: str) -> int:
    """Settle one chunk of muma rows against the server: read all, write the difference."""
    pending = _rows_to_write(server_cursor, rows)
    matched = 0
    for start in range(0, len(pending), WRITE_BATCH):
        matched += _write_batch(server_conn, server_cursor, pending[start : start + WRITE_BATCH], stats, source)
    return matched


def sync_song_versions_to_server(muma_conn, server_conn, source: str = 'unknown') -> dict:
    """Write muma's version model into the server database. Returns what it did.

    `source` names which server database this is. There is more than one -- a stable and an
    alpha instance -- and a line that does not say which one it skipped costs somebody the
    time to go and find out.
    """
    stats = {'considered': 0, 'matched': 0, 'skipped_no_columns': 0, 'chunks_skipped': 0}
    server_cursor = server_conn.cursor()
    if not _server_has_columns(server_cursor):
        logger.info('%s: no version columns yet, skipping the song-version sync', source)
        stats['skipped_no_columns'] = 1
        return stats

    try:
        server_conn.execute(BUSY_TIMEOUT_STATEMENT)
        with muma_conn.cursor() as muma_cursor:
            muma_cursor.execute(_TRACKS)
            while True:
                rows = muma_cursor.fetchmany(CHUNK)
                if not rows:
                    break
                stats['considered'] += len(rows)
                stats['matched'] += _write_chunk(server_conn, server_cursor, rows, stats, source)
    except Exception as e:
        logger.error('%s: song-version sync failed: %s', source, e, exc_info=True)

    logger.info(
        '%s: song-version sync considered %s tracks, matched %s in the server database',
        source,
        stats['considered'],
        stats['matched'],
    )
    return stats
