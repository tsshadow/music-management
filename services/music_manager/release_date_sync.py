"""Copy the release date the servers read off a file back into muma.

The server owns this one. It reads every tag at scan time and stores `ORIGINALDATE` in
`track.original_date` and `DATE` in `track.date`; muma's own copy lives in
`library_track_audio_features.release_date` and is written by the ml-analyzer, which has
only ever processed a quarter of the library -- 89.869 feature rows against 352.977 tracks
on production, with the date column filled exactly zero times. The feeds filter on a
release date, so both of them returned nothing at all until this sync existed. See
migrate_v24_track_release_date.sql.

**Every server is read in one pass, and that is the whole shape of this module.** Production
runs two: `stable`, which is what people play from, and `alpha`, whose database was last
written six weeks ago and holds 330.153 tracks against stable's 338.662, with 194.816 dated
against 238.207. Written as a per-server pass -- the way the users, playlist, artwork and
song-version syncs are -- whichever server ran last would decide, so alpha would clear
roughly 43.000 dates every hour and blank the 8.500 tracks it has never seen. A fact read
*out of* the servers has to be settled across all of them before anything is written; that
is the opposite direction from the syncs that write muma's own model *into* each server, and
it needs the opposite structure.

**The bridge is the file path**, the same one the song-version sync writes over in the other
direction: an LMS track id and a muma track id are unrelated, and `library_paths` already
knows every spelling worth trying. Reusing it rather than writing a second matcher is
deliberate -- see the note at the top of song_version_sync.py.

**Files must agree, across servers as well as within a track.** A track can have several media
files (a FLAC and an MP3 of the same recording) and each server can hold its own reading of
them. Every full date anyone has for the track goes into one set: one value wins, more than
one is a disagreement and leaves the track unknown. A year-only tag beside a full date is not
a disagreement unless the years differ -- a file tagged `2026` and one tagged `2026-09-04` are
the same release at two precisions, while `2019` beside `2026-09-04` is a contradiction and
counts as one.

**Three states, and the difference between two of them matters.** NULL means nobody has told
us anything -- no server holds a file for this track -- and the feed query then still falls
back to the audio-features column. The empty string means a server *does* hold the file and
there is no date to agree on, which is a decision and not a gap, so the feed honours it
instead of falling back to a stale analyzer value. A ten-character string is the agreed date.
`services/music_manager/feeds/queries.py` reads exactly that distinction.
"""

import logging
import sqlite3
import time

from services.music_manager.library_paths import server_candidate_paths

logger = logging.getLogger(__name__)

#: How many track ids to take in one pass. A window over the id range rather than a
#: `LIMIT`: a track's media files must all land in the same chunk, or two files of one
#: track end up compared against each other across a chunk boundary and the agreement
#: rule silently reads one file at a time.
ID_WINDOW = 5000

#: How long a read waits for a server to let go. A server writes to lms.db in WAL mode, so a
#: reader is not normally blocked at all, but a checkpoint still can be -- and this runs right
#: after a deploy, while the server is scanning.
BUSY_TIMEOUT_STATEMENT = 'PRAGMA busy_timeout = 30000'

#: What a server knows about one file. `original_date` is the release date the tagger wrote;
#: `date` is the edition -- for a SoundCloud or YouTube rip that is yt-dlp's upload date, which
#: is the honest "new" for those. Same COALESCE the server's own queries use (`Track.cpp`,
#: `effectiveDateExpr`).
_SERVER_DATE = """
    SELECT COALESCE(NULLIF(original_date, ''), date) AS release_date
    FROM track
    WHERE absolute_file_path = ?
"""

_MUMA_FILES = """
    SELECT t.id AS track_id, t.release_date AS current, mf.file_path
    FROM library_tracks t
    JOIN library_media_files mf ON mf.track_id = t.id
    WHERE t.id >= %s AND t.id < %s AND mf.file_path IS NOT NULL
"""

_UPDATE = 'UPDATE library_tracks SET release_date = %s WHERE id = %s'

#: What one file's lookup can come back as, beside a date string. `MISSING` is the one that
#: must never be confused with "no date": a server that does not have the file has no opinion
#: about it, and treating that as "no date" is what let a stale server clear the library.
MISSING = 'missing'
UNDATED = 'undated'


def _has_columns(server_cursor) -> bool:
    """Whether this server database has the date columns at all.

    An older server, or one still migrating after a deploy, is skipped rather than failed --
    the next pass finds them.
    """
    server_cursor.execute('PRAGMA table_info(track)')
    columns = {row[1] for row in server_cursor.fetchall()}
    return {'original_date', 'date', 'absolute_file_path'} <= columns


def _has_tracks(server_cursor) -> bool:
    """Whether this server has scanned anything yet.

    A server with an empty track table is mid-rebuild, not one that lost every release date.
    It is dropped from the pass rather than allowed to contribute `MISSING` for the whole
    library, which is the same distinction the rest of this module turns on.
    """
    server_cursor.execute('SELECT EXISTS (SELECT 1 FROM track)')
    return bool(server_cursor.fetchone()[0])


def _lookup(server_cursor, file_path: str) -> str:
    """One server's answer for one file: whatever date it holds, UNDATED, or MISSING.

    A partial value is passed on rather than dropped here. It is not a date this column can
    store, but it is still evidence about the year, and `resolve` is where that is weighed.
    """
    for path in server_candidate_paths(file_path):
        server_cursor.execute(_SERVER_DATE, (path,))
        row = server_cursor.fetchone()
        if row is None:
            continue
        # A file the server has but cannot date is answered, not searched past: the other
        # spellings are the same file.
        value = (row[0] or '').strip()
        return value or UNDATED
    return MISSING


def resolve(answers: list[str]) -> str | None:
    """What every server together says about one track: a date, `''`, or None to leave it alone.

    None is "nobody holds this file". `''` is "somebody holds it and there is no date anyone
    agrees on". Kept as a free function because it is the whole decision and deserves to be
    tested without a database on either side.
    """
    if all(answer == MISSING for answer in answers):
        return None

    values = {answer for answer in answers if answer not in (MISSING, UNDATED)}
    full = {value for value in values if len(value) == 10}

    # Exactly one day-precision date, or nothing. Two different days are a contradiction
    # whichever server they came from, and a year on its own is not a date this can store.
    if len(full) != 1:
        return ''

    agreed = full.pop()
    # A shorter value beside it is the same release at a coarser precision -- unless it names a
    # different year, which is a contradiction and not a precision. `2026` beside `2026-09-04`
    # agrees; `2019` beside it does not.
    if any(not agreed.startswith(value[:4]) for value in values - full):
        return ''
    return agreed


def _windows(muma_cursor) -> range:
    muma_cursor.execute('SELECT MIN(id) AS low, MAX(id) AS high FROM library_tracks')
    bounds = muma_cursor.fetchone() or {}
    low, high = bounds.get('low'), bounds.get('high')
    if low is None:
        return range(0)
    return range(low, high + 1, ID_WINDOW)


def _resolve_window(muma_cursor, server_cursors, low: int, high: int) -> tuple[list[tuple], int]:
    """Every track in [low, high) whose stored date differs from what the servers say."""
    muma_cursor.execute(_MUMA_FILES, (low, high))
    rows = muma_cursor.fetchall()

    answers: dict[int, list[str]] = {}
    current: dict[int, str | None] = {}
    for row in rows:
        track_id = row['track_id']
        current[track_id] = row['current']
        answers.setdefault(track_id, []).extend(_lookup(cursor, row['file_path']) for cursor in server_cursors)

    updates = []
    for track_id, found in answers.items():
        resolved = resolve(found)
        # None means no server holds the file, which is not the same as "there is no date":
        # the row keeps whatever it had rather than being cleared by a server that has never
        # seen the music.
        if resolved is not None and resolved != current[track_id]:
            updates.append((resolved, track_id))
    return updates, len(answers)


def _usable(server_conn, source: str, stats: dict):
    """A cursor for a server worth reading, or None with the reason logged."""
    cursor = server_conn.cursor()
    if not _has_columns(cursor):
        logger.info('%s: no date columns on track, leaving it out of the release-date sync', source)
        stats['skipped_no_columns'] += 1
        return None
    if not _has_tracks(cursor):
        logger.info('%s: server database holds no tracks, leaving it out of the release-date sync', source)
        stats['skipped_empty'] += 1
        return None
    server_conn.execute(BUSY_TIMEOUT_STATEMENT)
    return cursor


def sync_release_dates(muma_conn, servers: list) -> dict:
    """Settle `library_tracks.release_date` against every server at once. Returns what it did.

    `servers` is the list of `(sqlite connection, source name)` this pass may read. Being handed
    open connections rather than paths keeps this testable and leaves the caller in charge of
    what counts as a server, which is where that already lives.
    """
    stats = {'considered': 0, 'written': 0, 'cleared': 0, 'skipped_no_columns': 0, 'skipped_empty': 0, 'servers': 0}

    cursors = []
    for server_conn, source in servers:
        cursor = _usable(server_conn, source, stats)
        if cursor is not None:
            cursors.append(cursor)
    stats['servers'] = len(cursors)
    if not cursors:
        logger.info('release-date sync: no server database worth reading, nothing to do')
        return stats

    started = time.monotonic()
    try:
        with muma_conn.cursor() as muma_cursor:
            for start in _windows(muma_cursor):
                updates, considered = _resolve_window(muma_cursor, cursors, start, start + ID_WINDOW)
                stats['considered'] += considered
                if not updates:
                    continue
                muma_cursor.executemany(_UPDATE, updates)
                muma_conn.commit()
                stats['written'] += sum(1 for value, _ in updates if value)
                stats['cleared'] += sum(1 for value, _ in updates if not value)
    except sqlite3.OperationalError as e:
        # A locked server database is the server working, not an error: this pass ends and
        # the next hour reads the same rows again.
        logger.warning('release-date sync gave up on a locked server database: %s', e)
    except Exception as e:
        logger.error('release-date sync failed: %s', e, exc_info=True)

    # The duration is logged because nothing else measures it: this walks every media file
    # against every server, and that is the one number that decides whether the hourly cadence
    # is still sane.
    logger.info(
        'release-date sync read %s server(s), considered %s tracks, wrote %s, cleared %s in %.1fs',
        stats['servers'],
        stats['considered'],
        stats['written'],
        stats['cleared'],
        time.monotonic() - started,
    )
    return stats
