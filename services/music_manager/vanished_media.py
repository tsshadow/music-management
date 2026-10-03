"""The scanner's pass that removes the media rows of files gone from disk (GitLab issue #170).

Nothing else deletes a `library_media_files` row when its file disappears: a release folder that
moves or is deleted leaves its rows behind, with the right hash and no file. On production
8,372 of 354,222 rows were like that on 2026-10-03.

After every full walk the scanner calls `drop_vanished_media` with the set of paths the walk saw.
A row under the music root whose path the walk did not see is a candidate; a listing of its folder
decides whether the file is really gone (`services/common/vanished_files.py`, the same guards as
the operator script `stale_media_rows.py --gone`). The pass stops, deleting nothing, when a
library root is missing or empty, a folder cannot be listed, or more than 10% of the rows look
gone: that is a share that is not mounted, not a library that moved.

Only the media row is deleted, never the track: ratings key on `track_uid` and listens on the
track id, so the track row is what keeps a person's history.

* A file moved within the library: the walk already gave the new path its row, on the same track
  when the tags are unchanged (same `track_uid`). The track keeps a file and loses nothing.
* A file moved and retagged: the new path is on a new track and the old one is left without a
  file. The pass relinks it right away on the metadata key of `relink-orphans`
  (`track_relink.find_relink_target`): ratings, listens and works move to the one track it
  became. Without exactly one such track it stays a fileless track for
  `POST /api/scanner/relink-orphans` and `purge-orphans` to decide.

Rows with a wrong hash are not touched: those are bug report 093's stale rows, which the operator
script folds into their live track.
"""

from __future__ import annotations

import logging
from collections import Counter
from typing import Any

from services.common import vanished_files
from services.music_manager.database import transaction
from services.music_manager.scrobble_matching import normalize
from services.music_manager.track_relink import (
    build_metadata_index,
    find_relink_target,
    relink_track,
    track_has_media_file,
)

logger = logging.getLogger('music-manager.scanner')

#: Every media row the scanner itself would find again: its hash is the SHA-256 of its path.
LIVE_MEDIA_ROWS = 'SELECT id, file_path, track_id FROM library_media_files WHERE file_path_hash = SHA2(file_path, 256)'

#: One row, locked, for the re-check right before its delete.
_LOCK_ROW = 'SELECT id, file_path, file_path_hash, track_id FROM library_media_files WHERE id = %s FOR UPDATE'

#: The tracks a pass left without a file, as `find_relink_target` reads them.
_TRACKS_BY_ID = 'SELECT id, title, duration_secs, primary_artist_id FROM library_tracks WHERE id IN ({})'


def empty_totals() -> dict[str, int]:
    """The counters one pass reports, all at zero."""
    return {
        'rows': 0,
        'unseen': 0,
        'gone': 0,
        'deleted': 0,
        'changed': 0,
        'left_without_file': 0,
        'relinked': 0,
        'kept_without_file': 0,
        'failed': 0,
        'ratings_moved': 0,
        'ratings_merged': 0,
        'listens_moved': 0,
        'listens_dropped': 0,
    }


def _under(root: str, path: str) -> bool:
    """Whether `path` lies inside the music root the walk covered."""
    return path.startswith(root.rstrip('/') + '/')


def drop_vanished_media(conn: Any, music_root: str, seen: set[str]) -> dict[str, int]:
    """Delete the media rows under `music_root` whose file is gone; relink what that left fileless.

    `seen` is every file path the full walk met. Raises `vanished_files.LibraryUnreadable`, with
    nothing deleted, when the library looks unmounted (see the module docstring). Each deleted row
    is re-checked under a row lock first: its path unchanged and nothing at that path. Each track
    is its own transaction, so one failure leaves the rest of the pass in place.
    """
    totals = empty_totals()
    rows, gone_rows = _find_gone(conn, music_root, seen, totals)
    if not gone_rows:
        return totals
    by_track: dict[Any, list[dict]] = {}
    for row in gone_rows:
        by_track.setdefault(row['track_id'], []).append(row)
    gone_ids = {row['id'] for row in gone_rows}
    kept_by_track = Counter(row['track_id'] for row in rows if row['id'] not in gone_ids)
    orphans, index = _relink_inputs(
        conn, sorted(track for track in by_track if track is not None and not kept_by_track[track])
    )
    for track_id, track_rows in by_track.items():
        try:
            _drop_track_rows(conn, track_rows, (orphans.get(track_id), index), totals)
        except Exception as exc:
            totals['failed'] += 1
            logger.warning('Removing the vanished files of track %s failed: %s', track_id, exc)
    return totals


def _find_gone(conn: Any, music_root: str, seen: set[str], totals: dict[str, int]) -> tuple[list[dict], list[dict]]:
    """Every live row under the music root, and the ones whose file is gone; guards raise first."""
    with conn.cursor() as cursor:
        cursor.execute(LIVE_MEDIA_ROWS)
        rows = [row for row in cursor.fetchall() if _under(music_root, row['file_path'])]
    unseen = [row for row in rows if row['file_path'] not in seen]
    totals['rows'], totals['unseen'] = len(rows), len(unseen)
    if not unseen:
        return rows, []
    # The walk skips hidden folders and any folder it cannot read; the listing settles both.
    gone = vanished_files.gone_paths([row['file_path'] for row in unseen], music_root)
    vanished_files.check_gone_share(len(gone), len(rows))
    gone_rows = [row for row in unseen if row['file_path'] in gone]
    totals['gone'] = len(gone_rows)
    return rows, gone_rows


def _relink_inputs(conn: Any, fileless: list[int]) -> tuple[dict[int, dict], dict[str, list[dict]]]:
    """The tracks the pass will leave fileless, and the metadata index their successors come from."""
    if not fileless:
        return {}, {}
    with conn.cursor() as cursor:
        cursor.execute(_TRACKS_BY_ID.format(', '.join(['%s'] * len(fileless))), tuple(fileless))
        orphans = {int(row['id']): row for row in cursor.fetchall()}
        titles = {
            normalize(row['title'])
            for row in orphans.values()
            if row.get('title') and row.get('duration_secs') is not None and row.get('primary_artist_id')
        }
        index = build_metadata_index(cursor, {title for title in titles if title})
    # A track this pass is about to leave fileless is no successor, whatever its metadata.
    leaving = set(fileless)
    index = {title: [row for row in found if row['id'] not in leaving] for title, found in index.items()}
    return orphans, index


def _drop_track_rows(
    conn: Any, track_rows: list[dict], relink: tuple[dict | None, dict[str, list[dict]]], totals: dict[str, int]
) -> None:
    """Delete one track's gone rows and, when that leaves it without a file, relink it; one transaction.

    `relink` is the track as `find_relink_target` reads it (None without a track) and the
    metadata index. The counts reach `totals` only once the transaction committed.
    """
    track_id = track_rows[0]['track_id']
    orphan, index = relink
    counts: Counter = Counter()
    with conn.cursor() as cursor, transaction(conn):
        for row in track_rows:
            counts['deleted' if _delete_if_still_gone(cursor, row) else 'changed'] += 1
        if counts['deleted'] and track_id is not None and not track_has_media_file(cursor, track_id):
            counts['left_without_file'] += 1
            target = find_relink_target(cursor, orphan, index) if orphan else None
            moved = relink_track(cursor, track_id, target) if target is not None else None
            if moved is None:
                counts['kept_without_file'] += 1
            else:
                counts['relinked'] += 1
                for name in ('ratings_moved', 'ratings_merged', 'listens_moved', 'listens_dropped'):
                    counts[name] += moved[name]
    for name, value in counts.items():
        totals[name] += value


def _delete_if_still_gone(cursor: Any, row: dict) -> bool:
    """Delete one media row if, with it locked, it still names the same path and nothing is there."""
    cursor.execute(_LOCK_ROW, (row['id'],))
    current = cursor.fetchone()
    if current is None or current['file_path'] != row['file_path']:
        return False
    if vanished_files.path_exists(current['file_path']):
        return False
    cursor.execute('DELETE FROM library_media_files WHERE id = %s', (row['id'],))
    return True


def summary(totals: dict[str, int]) -> str:
    """One line for the event log: what went, what moved, what is left for relink-orphans."""
    return (
        f"Removed {totals['deleted']} media rows whose file is gone ({totals['changed']} came back or changed "
        f"and were kept). {totals['left_without_file']} tracks lost their last file: {totals['relinked']} "
        f"relinked to the track their file became (ratings moved {totals['ratings_moved']}, merged "
        f"{totals['ratings_merged']}; listens moved {totals['listens_moved']}), {totals['kept_without_file']} "
        f'kept without a file for relink-orphans, {totals["failed"]} failed.'
    )
