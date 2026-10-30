"""Push what muma decided about song versions into the server's own database.

muma owns the model: it has the label provenance and the download archives that decide
which version of a song wins, and LMS has neither. So LMS gets four columns on `track`
(migration 118) and muma fills them here, in the same lms.db pass that already syncs
users, playlists and artist images. No endpoint, no API key, no HTTP in the browsing
path -- see the design note in docs/designs/song-versions/technical.md.

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

**Exactly one server row per work is canonical** (bug report 097). A muma track can own
several files -- the FLAC and the MP3 of one release -- and pushing "canonical" per file
marked every one of them, so the app showed the song twice. And when the server had none of
the canonical track's files, every version it did have was marked non-canonical and the song
vanished from canonical-only lists. So the work, not the file, is the unit: the canonical
track's best file wins, and if the server lacks all of that track's files, the best version
the server does have stands in. Ungrouped tracks keep every file canonical -- the server
shows a row without a work regardless, so there is nothing to choose between.

Read first, write the difference. The server database is the player's, and the player
does not wait for it: a Dbo transaction reads before it writes, and SQLite answers a
read-to-write upgrade with SQLITE_BUSY the moment another connection holds the write lock
-- the busy timeout only applies to a connection with no transaction open. So while this
job held that lock, a rating from the app was a 500 and a scrobble was lost. This job
therefore reads every chunk without a transaction (reads take no write lock in WAL mode),
keeps only the rows the server disagrees with, and writes those in transactions short
enough to be gone before anyone notices. After the first pass almost nothing disagrees and
almost nothing is written. An UPDATE of four columns keyed on an indexed path is a
different class of operation from the DROP TABLE that once took production down
(docs/bug-reports/005), but the same care applies: short statements, no schema changes.

The other direction -- LMS holding the lock while this job wants it -- is `lms_writes`: the
scanner holds it for hours at a stretch, so a busy server defers the rows rather than
losing them, and the hourly loop writes exactly those rows again a few minutes later
(bug report 129).
"""

import logging
from typing import NamedTuple

from services.common.config_store import ConfigStore
from services.music_manager.library_paths import candidate_paths
from services.music_manager.lms_writes import BUSY_TIMEOUT_STATEMENT, PendingWrites
from services.music_manager.song_versions import derived_bitrate, format_tier

logger = logging.getLogger(__name__)

#: How many tracks to read from muma at a time. The join is cheap; the chunk bounds how
#: much sits in memory, not how long a write transaction lasts -- lms_writes.WRITE_BATCH does that.
CHUNK = 2000

#: What muma knows about every media file, one row per `library_media_files` row. Which LMS
#: row of a work is canonical is decided per work in Python (`_settle_work`), not here: the
#: answer depends on which files the server actually has, and only the server can say that.
#:
#: Sorted exactly like the track-form push (bug report 093) so every row naming one path
#: arrives together and the row to trust comes first: the scanner's own (its hash is the
#: hash of the path it holds), then the newest. Byte order, because the column's collation is
#: case-insensitive and two spellings LMS keeps apart must not interleave.
_FILES = """
    SELECT mf.id AS media_id,
           mf.file_path,
           mf.file_size,
           COALESCE(mf.duration_secs, t.duration_secs) AS duration_secs,
           mf.file_path_hash = SHA2(mf.file_path, 256) AS own_row,
           t.id AS track_id,
           t.work_id,
           COALESCE(t.version_kind, '') AS version_kind,
           COALESCE(t.version_score, 0) AS version_score,
           w.canonical_track_id
    FROM library_media_files mf
    JOIN library_tracks t ON t.id = mf.track_id
    LEFT JOIN library_works w ON w.id = t.work_id
    WHERE mf.file_path IS NOT NULL
    ORDER BY CAST(mf.file_path AS BINARY),
             mf.file_path_hash = SHA2(mf.file_path, 256) DESC,
             mf.id DESC
"""

#: Keyed on the server's own row id, found by the read below, and comparing before it
#: writes: a row another writer already settled between the read and the write is left
#: alone, so the number of changed rows is exactly the number of rows that were wrong.
_UPDATE = (
    'UPDATE track SET work_id = ?1, is_canonical = ?2, version_kind = ?3, version_score = ?4 '
    'WHERE id = ?5 AND (work_id IS NOT ?1 OR is_canonical IS NOT ?2 '
    'OR version_kind IS NOT ?3 OR version_score IS NOT ?4)'
)

#: What the server currently says about this file. Read before anything is written, so a
#: row that already agrees costs a read and no write -- and, more to the point, no write
#: *transaction*. An UPDATE whose WHERE matches nothing still takes SQLite's write lock
#: from the moment it runs until the commit, and that is what the player ran into.
_CURRENT = (
    'SELECT id, work_id, is_canonical, version_kind, version_score FROM track WHERE absolute_file_path = ? LIMIT 1'
)


class _ServerFile(NamedTuple):
    """One file the server has, with what muma knows about its track. Kept per work until
    every file of the library has been read, so it holds ints rather than paths."""

    server_id: int
    current: tuple
    track_id: int
    work_id: int
    version_kind: str
    version_score: int
    canonical_track_id: int | None
    rank: tuple


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


def first_per_path(rows, previous_path: str | None, stats: dict) -> tuple[list, str | None]:
    """The first row of every path, given rows sorted by path; the rest are counted and dropped.

    Two `library_media_files` rows can name one file -- the scanner's own and a stale one
    whose hash is no longer its path's (bug report 093) -- and pushing both gives one server
    row two answers. `previous_path` carries the last path of the previous chunk, so a path
    whose rows straddle a chunk boundary is still pushed once. Returns the kept rows and the
    new last path. Shared with track_form_sync, which pushes by the same rule.
    """
    kept = []
    for row in rows:
        if row['file_path'] == previous_path:
            stats['duplicates_skipped'] = stats.get('duplicates_skipped', 0) + 1
            continue
        previous_path = row['file_path']
        kept.append(row)
    return kept, previous_path


def file_rank(row, prefer_lossless: bool = True) -> tuple:
    """How good one file of a track is as the one to show; lower sorts first.

    The scanner's own row first (bug report 093), then the best quality by the song-version
    format tiers and the bitrate derived from size and length, then the newest row. Every key
    is a stored value, so the same library picks the same file on every pass.

    `prefer_lossless` is the same setting the ranking reads (docs/designs/song-versions/), so
    the file LMS shows for a track follows the format order that chose the track.
    """
    bitrate = derived_bitrate(row['file_size'], row['duration_secs'])
    return (
        0 if row['own_row'] else 1,
        format_tier(row['file_path'] or '', bitrate, prefer_lossless),
        -bitrate,
        -int(row['media_id'] or 0),
    )


def _find_on_server(server_cursor, file_path: str):
    """The server's row for this file, trying every spelling of the path, or None.

    muma scans /mnt/music and the server was told /music. A path the server knows nothing
    about is a file it does not have, which is not an error -- the two libraries are allowed
    to differ.
    """
    for path in candidate_paths(file_path):
        server_cursor.execute(_CURRENT, (path,))
        current = server_cursor.fetchone()
        if current is not None:
            return current
    return None


def _settle_work(files: list[_ServerFile], stats: dict) -> list[tuple]:
    """Exactly one canonical server row for this work, as `(values, server_id)` pairs.

    The canonical track is the one the work names. If the server has none of its files --
    the file is missing there, or its path does not map -- the best version the server does
    have takes its place, ranked the way song_version_worker ranks: score, then its best
    file, then the oldest track id. A work without a named canonical is handled the same
    way. Without that fallback every version of the song was non-canonical in the server,
    and the song vanished from every canonical-only list. Within the chosen track one file
    wins (`file_rank`); its other files are copies of the same recording and are not.
    """
    by_track: dict[int, list[_ServerFile]] = {}
    for entry in files:
        by_track.setdefault(entry.track_id, []).append(entry)
    named = files[0].canonical_track_id
    if named in by_track:
        chosen = named
    else:
        stats['canonical_fallbacks'] += 1
        chosen = min(
            by_track,
            key=lambda track_id: (
                -by_track[track_id][0].version_score,
                min(entry.rank for entry in by_track[track_id]),
                track_id,
            ),
        )
    winner = min(by_track[chosen], key=lambda entry: entry.rank)
    pending = []
    for entry in files:
        values = _as_stored((entry.work_id, 1 if entry is winner else 0, entry.version_kind, entry.version_score))
        if entry.current != values:
            pending.append((values, entry.server_id))
    return pending


def _read_chunk(server_cursor, rows, works: dict, seen: set, stats: dict, prefer_lossless: bool = True) -> list[tuple]:
    """Look one chunk up in the server. Ungrouped files are settled at once and returned as
    pending writes; files of a work are parked in `works` until the whole library is read,
    because a work's files can sit anywhere in the path order."""
    pending = []
    for row in rows:
        current = _find_on_server(server_cursor, row['file_path'])
        if current is None:
            continue
        server_id = int(current[0])
        if server_id in seen:
            # Two muma spellings of one server file: the first one read decides.
            continue
        seen.add(server_id)
        stored = _as_stored(current[1:])
        if row['work_id'] is None:
            # Not grouped yet: canonical, no work. The server shows a row without a work
            # whatever is_canonical says, so this is what keeps ungrouped music visible.
            values = _as_stored((None, 1, row['version_kind'], row['version_score']))
            if stored != values:
                pending.append((values, server_id))
            continue
        work_id = int(row['work_id'])
        works.setdefault(work_id, []).append(
            _ServerFile(
                server_id=server_id,
                current=stored,
                track_id=int(row['track_id']),
                work_id=work_id,
                version_kind=str(row['version_kind'] or ''),
                version_score=int(row['version_score'] or 0),
                canonical_track_id=None if row['canonical_track_id'] is None else int(row['canonical_track_id']),
                rank=file_rank(row, prefer_lossless),
            )
        )
    return pending


def sync_song_versions_to_server(
    muma_conn,
    server_conn,
    source: str = 'unknown',
    prefer_lossless: bool | None = None,
    deferred: list[PendingWrites] | None = None,
) -> dict:
    """Write muma's version model into the server database. Returns what it did.

    Two phases. The first streams every muma file in path order, keeps one row per path,
    finds the server's row for it, writes ungrouped files straight away and parks the rest
    per work. The second gives every work exactly one canonical server row (`_settle_work`)
    and writes what the server disagrees with. `matched` is the number of server rows
    actually changed, so a second run over an unchanged library reports 0.

    `source` names which server database this is. There is more than one -- a stable and an
    alpha instance -- and a line that does not say which one it skipped costs somebody the
    time to go and find out.

    `prefer_lossless` defaults to the configured setting, read once per pass.

    A server busy scanning defers what it refused (`lms_writes`); `deferred` receives those rows
    as a `PendingWrites` so the caller can write them again later, and `stats['deferred']`
    counts them. Nothing refused is dropped: the next pass would find the same difference.
    """
    if prefer_lossless is None:
        prefer_lossless = getattr(ConfigStore(), 'prefer_lossless', True) is not False
    stats = {
        'considered': 0,
        'matched': 0,
        'skipped_no_columns': 0,
        'deferred': 0,
        'duplicates_skipped': 0,
        'works': 0,
        'canonical_fallbacks': 0,
    }
    server_cursor = server_conn.cursor()
    if not _server_has_columns(server_cursor):
        logger.info('%s: no version columns yet, skipping the song-version sync', source)
        stats['skipped_no_columns'] = 1
        return stats

    writes = PendingWrites(_UPDATE)
    try:
        server_conn.execute(BUSY_TIMEOUT_STATEMENT)
        works: dict[int, list[_ServerFile]] = {}
        seen: set[int] = set()
        with muma_conn.cursor() as muma_cursor:
            muma_cursor.execute(_FILES)
            previous_path = None
            while True:
                rows = muma_cursor.fetchmany(CHUNK)
                if not rows:
                    break
                stats['considered'] += len(rows)
                rows, previous_path = first_per_path(rows, previous_path, stats)
                pending = _read_chunk(server_cursor, rows, works, seen, stats, prefer_lossless)
                stats['matched'] += writes.write(server_conn, server_cursor, pending)
        stats['works'] = len(works)
        pending = []
        for files in works.values():
            pending.extend(_settle_work(files, stats))
        stats['matched'] += writes.write(server_conn, server_cursor, pending)
    except Exception as e:
        logger.error('%s: song-version sync failed: %s', source, e, exc_info=True)

    stats['deferred'] = len(writes.rows)
    if writes.rows and deferred is not None:
        deferred.append(writes)
    logger.info(
        '%s: song-version sync considered %s files (%s duplicate rows skipped), wrote %s, '
        'deferred %s because the server database was busy; '
        '%s works, %s of them canonical through a fallback because the server lacks the chosen file',
        source,
        stats['considered'],
        stats['duplicates_skipped'],
        stats['matched'],
        stats['deferred'],
        stats['works'],
        stats['canonical_fallbacks'],
    )
    return stats
