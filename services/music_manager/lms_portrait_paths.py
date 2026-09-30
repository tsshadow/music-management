"""Move the artist-portrait rows muma wrote into lms.db onto the path LMS itself sees.

Until bug report 138 the portrait sync (`routers/artist_images.sync_artist_images_to_server`)
wrote each portrait into LMS's `image` table under muma's own mount, `/mnt/music/artists/...`.
LMS mounts the same share at `/music`, so to LMS those files did not exist: every library-wide
scan (`ScanStepCheckForRemovedFiles`) removed all of them -- about 20,000 rows on production,
0.2 s each because nothing indexed the columns the artwork cascade nulls -- and the hourly sync
wrote them back under new ids. The sync now writes the server's spelling
(`library_paths.server_path`); this pass repairs the rows written before that.

For each row still under muma's mount:

- **LMS has no row for that file yet**: the row is renamed in place. Its image id, its artwork
  and every artist pointing at it stay as they are; LMS's scanner later finds it by path and
  fills in the directory and write time instead of adding a second row.
- **LMS already indexed the file itself** (`/music/artists` sits inside its library root, so on
  production it has, for nearly every portrait): renaming would give one path two rows, and
  LMS's `Image::find(path)` expects one. Instead every artist pointing at the old row's artwork
  is moved onto LMS's artwork for the same file, and the old row is left for LMS's removed-files
  check -- a delete that costs microseconds once its indexes exist, and one this connection
  should not do: without `PRAGMA foreign_keys` the cascade would not run, and with it the write
  lock would be held for the whole unindexed cascade on a server without those indexes.

Write discipline is `lms_writes`': reads happen outside any transaction, each batch of at most
WRITE_BATCH rows takes the write lock up front with `BEGIN IMMEDIATE`, and the first batch that
finds the server busy ends the pass. Nothing is lost by stopping -- the rows are simply still
there, and the next hourly sync picks them up. Once everything is repaired a pass is one indexed
range read and writes nothing.
"""

import contextlib
import logging
import sqlite3
from typing import Any

from services.music_manager.library_paths import LMS_MUSIC_ROOT, MUMA_MUSIC_ROOT, server_path
from services.music_manager.lms_writes import BUSY_TIMEOUT_STATEMENT, WRITE_BATCH, is_lock_error

logger = logging.getLogger(__name__)

# A range rather than LIKE: LIKE is case-insensitive in SQLite and cannot use `image_path_idx`,
# a range on the same column can. '0' is the character after '/', so this is "starts with
# <root>/" exactly.
_ROWS_UNDER_MUMA_ROOT = (
    'SELECT id, absolute_file_path FROM image WHERE absolute_file_path >= ? AND absolute_file_path < ? ORDER BY id'
)


# Every artist pointing at a row under muma's mount, in one read. `artist.preferred_artwork_id`
# had no index before bug report 138, so asking per row scanned the artist table 6,000 times: 46
# seconds on a copy of production, every hour. Once, it is one pass over `artist`.
_ARTISTS_ON_MUMA_ROWS = (
    'SELECT a.id, aw.image_id FROM artist a '
    'JOIN artwork aw ON aw.id = a.preferred_artwork_id '
    'JOIN image im ON im.id = aw.image_id '
    'WHERE im.absolute_file_path >= ? AND im.absolute_file_path < ?'
)


def _plan(
    server_cursor: Any, rows: list[tuple[int, str]], artists_by_image: dict[int, list[int]]
) -> tuple[list[tuple], list[tuple]]:
    """Split `rows` into renames and artist moves, reading only. Returns (renames, moves).

    A rename is `(new_path, image_id)`. A move is `(new_artwork_id, artist_id)`, one per artist
    currently pointing at an old row whose file LMS indexed on its own (`artists_by_image`, old
    image id to the artists on it). An old row no artist points at needs nothing: LMS removes it
    on its next library scan.
    """
    renames: list[tuple] = []
    moves: list[tuple] = []
    claimed: set[str] = set()
    for image_id, path in rows:
        new_path = server_path(path)
        twin = server_cursor.execute(
            'SELECT id FROM image WHERE absolute_file_path = ? ORDER BY id LIMIT 1', (new_path,)
        ).fetchone()
        if twin is None and new_path not in claimed:
            # `claimed`: two old rows for the same file (the sync once inserted twice) must not
            # both be renamed onto one path; the second is treated as having a twin next pass.
            claimed.add(new_path)
            renames.append((new_path, image_id))
            continue
        if twin is None or image_id not in artists_by_image:
            continue
        artwork = server_cursor.execute(
            'SELECT id FROM artwork WHERE image_id = ? ORDER BY id LIMIT 1', (twin[0],)
        ).fetchone()
        if artwork is None:
            continue
        moves.extend((artwork[0], artist_id) for artist_id in artists_by_image[image_id])
    return renames, moves


def _write(server_conn: Any, server_cursor: Any, renames: list[tuple], moves: list[tuple]) -> bool:
    """One short write transaction, lock taken first. Returns False if the server was busy."""
    try:
        server_cursor.execute('BEGIN IMMEDIATE')
        server_cursor.executemany('UPDATE image SET absolute_file_path = ? WHERE id = ?', renames)
        server_cursor.executemany('UPDATE artist SET preferred_artwork_id = ? WHERE id = ?', moves)
        server_conn.commit()
        return True
    except sqlite3.OperationalError as e:
        # A failed BEGIN leaves nothing to roll back, and a rollback that fails must not replace
        # the error that explains what happened.
        with contextlib.suppress(Exception):
            server_conn.rollback()
        if not is_lock_error(e):
            raise
        return False


def repair_portrait_paths(server_conn: Any, source: str = 'unknown') -> dict:
    """Move every image row under muma's mount onto LMS's spelling. Returns what it did.

    `renamed` rows got the new path in place, `artists_moved` artists were moved onto the
    artwork of LMS's own row for the same file, `left_for_lms` old rows are waiting for LMS's
    removed-files check, and `deferred` is set when a busy server ended the pass early.
    Idempotent: a repaired database reads one empty range and writes nothing.
    """
    stats = {'renamed': 0, 'artists_moved': 0, 'left_for_lms': 0, 'deferred': False}
    if MUMA_MUSIC_ROOT == LMS_MUSIC_ROOT:
        return stats
    server_conn.execute(BUSY_TIMEOUT_STATEMENT)
    server_cursor = server_conn.cursor()
    under_muma_root = (MUMA_MUSIC_ROOT + '/', MUMA_MUSIC_ROOT + '0')
    rows = server_cursor.execute(_ROWS_UNDER_MUMA_ROOT, under_muma_root).fetchall()
    artists_by_image: dict[int, list[int]] = {}
    if rows:
        for artist_id, image_id in server_cursor.execute(_ARTISTS_ON_MUMA_ROWS, under_muma_root).fetchall():
            artists_by_image.setdefault(image_id, []).append(artist_id)
    for start in range(0, len(rows), WRITE_BATCH):
        batch = rows[start : start + WRITE_BATCH]
        renames, moves = _plan(server_cursor, batch, artists_by_image)
        if (renames or moves) and not _write(server_conn, server_cursor, renames, moves):
            stats['deferred'] = True
            break
        stats['renamed'] += len(renames)
        stats['artists_moved'] += len(moves)
        stats['left_for_lms'] += len(batch) - len(renames)
    if rows:
        logger.info(
            '%s: portrait path repair renamed %s rows, moved %s artists onto the server\'s own row, '
            'left %s old rows for its removed-files check%s',
            source,
            stats['renamed'],
            stats['artists_moved'],
            stats['left_for_lms'],
            ', stopped early because the server database was busy' if stats['deferred'] else '',
        )
    return stats
