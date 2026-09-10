"""Copy the release date the server read off a file back into muma.

The server owns this one. It reads every tag at scan time and stores `ORIGINALDATE` in
`track.original_date` and `DATE` in `track.date`; muma's own copy lives in
`library_track_audio_features.release_date` and is written by the ml-analyzer, which has
only ever processed a quarter of the library -- 89.869 feature rows against 352.977 tracks
on production, with the date column filled exactly zero times. The feeds filter on a
release date, so both of them returned nothing at all until this sync existed. See
migrate_v24_track_release_date.sql.

**The bridge is the file path**, the same one the song-version sync writes over in the other
direction: an LMS track id and a muma track id are unrelated, and `library_paths.candidate_paths`
already knows every spelling worth trying. Reusing it rather than writing a second matcher is
deliberate -- see the note at the top of song_version_sync.py.

**Two files under one track must agree.** A track can have several media files (a FLAC and an
MP3 of the same recording), and if they carry different dates there is no honest way to pick
one, so the track counts as having no date at all. That is the same rule
`feeds/queries.py`'s audio-features subquery applies, and the two have to keep agreeing:
a feed that filters on a date must never sort on a date that was chosen arbitrarily.

**A date that disappears is written back as NULL.** A stale value left behind would keep a
track in the radar forever after its tag was corrected, which is the failure mode this whole
column exists to avoid -- an empty feed is visible, a wrong feed is not.

Only a full ten-character date is taken. `date` is very often just a year ('2026'), and a
year padded out to the first of January would put a few thousand tracks in every radar
window. Length is the precision here; there is no separate precision column.
"""

import logging
import sqlite3

from services.music_manager.library_paths import candidate_paths

logger = logging.getLogger(__name__)

#: How many track ids to take in one pass. A window over the id range rather than a
#: `LIMIT`: a track's media files must all land in the same chunk, or two files of one
#: track end up compared against each other across a chunk boundary and the agreement
#: rule silently reads one file at a time.
ID_WINDOW = 5000

#: How long a read waits for the server to let go. The server writes to lms.db in WAL mode,
#: so a reader is not normally blocked at all, but a checkpoint still can be -- and this
#: runs right after a deploy, while the server is scanning.
BUSY_TIMEOUT_STATEMENT = 'PRAGMA busy_timeout = 30000'

#: What the server knows about one file. `original_date` is the release date the tagger
#: wrote; `date` is the edition -- for a SoundCloud or YouTube rip that is yt-dlp's upload
#: date, which is the honest "new" for those. Same COALESCE the server's own queries use
#: (`Track.cpp`, `effectiveDateExpr`).
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


def _server_has_columns(server_cursor) -> bool:
    """Whether this server database has the date columns at all.

    An older server, or one still migrating after a deploy, is skipped rather than failed --
    the next pass finds them.
    """
    server_cursor.execute('PRAGMA table_info(track)')
    columns = {row[1] for row in server_cursor.fetchall()}
    return {'original_date', 'date', 'absolute_file_path'} <= columns


def _date_for_path(server_cursor, file_path: str) -> str | None:
    """The server's date for one file, or None if it does not have the file or a full date."""
    for path in candidate_paths(file_path):
        server_cursor.execute(_SERVER_DATE, (path,))
        row = server_cursor.fetchone()
        if row is None:
            continue
        value = (row[0] or '').strip()
        # A file the server has but has no full date for is answered, not searched past:
        # the other spellings are the same file.
        return value if len(value) == 10 else None
    return None


def _resolve_window(muma_cursor, server_cursor, low: int, high: int) -> tuple[list[tuple], int]:
    """Every track in [low, high) whose stored date differs from the server's."""
    muma_cursor.execute(_MUMA_FILES, (low, high))
    rows = muma_cursor.fetchall()

    dates: dict[int, set[str | None]] = {}
    current: dict[int, str | None] = {}
    for row in rows:
        track_id = row['track_id']
        current[track_id] = row['current']
        dates.setdefault(track_id, set()).add(_date_for_path(server_cursor, row['file_path']))

    updates = []
    for track_id, found in dates.items():
        known = {value for value in found if value}
        # One agreed date, or nothing. Two files that disagree leave the track dateless,
        # and so does a track the server does not have.
        resolved = known.pop() if len(known) == 1 else None
        if resolved != current[track_id]:
            updates.append((resolved, track_id))
    return updates, len(dates)


def sync_release_dates_from_server(muma_conn, server_conn, source: str = 'unknown') -> dict:
    """Read the server's release dates into `library_tracks.release_date`. Returns what it did.

    `source` names which server database this is; there is more than one, and a line that
    does not say which one it skipped costs somebody the time to find out.
    """
    stats = {'considered': 0, 'written': 0, 'cleared': 0, 'skipped_no_columns': 0}
    server_cursor = server_conn.cursor()
    if not _server_has_columns(server_cursor):
        logger.info('%s: no date columns on track, skipping the release-date sync', source)
        stats['skipped_no_columns'] = 1
        return stats

    try:
        server_conn.execute(BUSY_TIMEOUT_STATEMENT)

        # A server with no tracks at all is one that is mid-rebuild, not one that lost every
        # release date. Without this the pass would clear the column library-wide and both feeds
        # would go empty for an hour -- the exact failure this column was added to end.
        server_cursor.execute('SELECT EXISTS (SELECT 1 FROM track)')
        if not server_cursor.fetchone()[0]:
            logger.info('%s: server database holds no tracks, skipping the release-date sync', source)
            return stats

        with muma_conn.cursor() as muma_cursor:
            muma_cursor.execute('SELECT MIN(id) AS low, MAX(id) AS high FROM library_tracks')
            bounds = muma_cursor.fetchone()
            low, high = (bounds or {}).get('low'), (bounds or {}).get('high')
            if low is None:
                return stats

            for start in range(low, high + 1, ID_WINDOW):
                updates, considered = _resolve_window(muma_cursor, server_cursor, start, start + ID_WINDOW)
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
        logger.warning('%s: release-date sync gave up on a locked server database: %s', source, e)
    except Exception as e:
        logger.error('%s: release-date sync failed: %s', source, e, exc_info=True)

    logger.info(
        '%s: release-date sync considered %s tracks, wrote %s, cleared %s',
        source,
        stats['considered'],
        stats['written'],
        stats['cleared'],
    )
    return stats
