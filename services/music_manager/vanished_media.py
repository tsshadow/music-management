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
  became. When that key finds no single track, the file-name key tries: the name of the gone
  file (extension included) on exactly one track that still has a file, with the same duration.
  Without exactly one such track it stays a fileless track for
  `POST /api/scanner/relink-orphans` and `purge-orphans` to decide.

The file-name key is for the import queue (GitLab issue #71). The importer extracts a weekly pack
into `import/<pack>/<release>/`. A full walk can index those files before the tagger writes them:
one unsplit artist such as `Bruhze & OTM`, no display artist. The importer then lifts the release
out of the pack and renames its folder. The tagged file has a new primary artist, so the metadata
key finds nothing, and an MP3 beside its FLAC is a second candidate within the duration tolerance.
The folder changes and the file name does not. On 2026-11-06 one pass left 134 fileless tracks.

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
    DURATION_TOLERANCE_SECS,
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

#: A track the pass leaves without a file, as `find_relink_target` reads it. One primary-key read
#: per track: a fixed statement, no IN list built from the ids.
_TRACK_BY_ID = 'SELECT id, title, duration_secs, primary_artist_id FROM library_tracks WHERE id = %s'


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
        'relinked_file_name': 0,
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


def _file_name(path: str) -> str:
    """The last part of a POSIX path, extension included, so `02.flac` and `02.mp3` stay apart."""
    return path.rsplit('/', 1)[-1]


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
    fileless, names = _left_fileless(by_track, _live_rows(rows, gone_rows))
    orphans, index = _relink_inputs(conn, fileless)
    for track_id, track_rows in by_track.items():
        try:
            _drop_track_rows(conn, track_rows, (orphans.get(track_id), index, names), totals)
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
        orphans = {}
        for track_id in fileless:
            cursor.execute(_TRACK_BY_ID, (track_id,))
            row = cursor.fetchone()
            if row is not None:
                orphans[int(row['id'])] = row
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


def _live_rows(rows: list[dict], gone_rows: list[dict]) -> list[dict]:
    """The rows of `rows` whose file is still there."""
    gone_ids = {row['id'] for row in gone_rows}
    return [row for row in rows if row['id'] not in gone_ids]


def _left_fileless(by_track: dict[Any, list[dict]], live: list[dict]) -> tuple[list[int], dict[str, set[int]]]:
    """The tracks that lose a file in this pass and keep no live row, in id order, and their file-name index."""
    kept_by_track = Counter(row['track_id'] for row in live)
    fileless = sorted(track for track in by_track if track is not None and not kept_by_track[track])
    return fileless, _file_name_index(live, set(fileless), by_track)


def _file_name_index(live: list[dict], fileless: set[int], by_track: dict[Any, list[dict]]) -> dict[str, set[int]]:
    """Map each file name a fileless track lost to the tracks that still have a file of that name.

    Built from the rows `_find_gone` already read, so it costs no query. A track this pass leaves
    fileless is no successor.
    """
    wanted = {_file_name(row['file_path']) for track in fileless for row in by_track.get(track, [])}
    names: dict[str, set[int]] = {}
    for row in live:
        if row['track_id'] is None or row['track_id'] in fileless:
            continue
        name = _file_name(row['file_path'])
        if name in wanted:
            names.setdefault(name, set()).add(int(row['track_id']))
    return names


def _same_duration(left: Any, right: Any) -> bool:
    """Whether two stored lengths are one recording. An unknown length matches nothing."""
    if left is None or right is None:
        return False
    return abs(float(left) - float(right)) < DURATION_TOLERANCE_SECS


def find_file_name_successor(
    cursor: Any, orphan: dict, track_rows: list[dict], names: dict[str, set[int]]
) -> int | None:
    """The one track with a live file of the same name and the same duration as a gone file of `orphan`.

    For a release whose folder moved while the tagger rewrote its files. The metadata key cannot
    follow an artist credit the tagger split, and an MP3 beside its FLAC is a second candidate
    there. The extension keeps those two apart. The duration keeps apart two releases that each
    have an `01-intro.mp3`. None when not exactly one track qualifies.
    """
    candidates: set[int] = set()
    for row in track_rows:
        candidates |= names.get(_file_name(row['file_path']), set())
    candidates.discard(orphan['id'])
    matches = []
    for candidate in sorted(candidates):
        cursor.execute(_TRACK_BY_ID, (candidate,))
        found = cursor.fetchone()
        if found is not None and _same_duration(found.get('duration_secs'), orphan.get('duration_secs')):
            matches.append(candidate)
    return matches[0] if len(matches) == 1 else None


def _successor(
    cursor: Any, relink: tuple[dict | None, dict[str, list[dict]], dict[str, set[int]]], track_rows: list[dict]
) -> tuple[int | None, bool]:
    """The track a fileless track became, and whether the file-name key found it.

    The metadata key first, the file-name key when that finds no single track. `relink` is as
    `_drop_track_rows` gets it.
    """
    orphan, index, names = relink
    if not orphan:
        return None, False
    target = find_relink_target(cursor, orphan, index)
    if target is not None:
        return target, False
    target = find_file_name_successor(cursor, orphan, track_rows, names)
    return target, target is not None


def _drop_track_rows(
    conn: Any,
    track_rows: list[dict],
    relink: tuple[dict | None, dict[str, list[dict]], dict[str, set[int]]],
    totals: dict[str, int],
) -> None:
    """Delete one track's gone rows and, when that leaves it without a file, relink it; one transaction.

    `relink` is the track as `find_relink_target` reads it (None without a track), the metadata
    index and the file-name index. The counts reach `totals` only once the transaction committed.
    """
    track_id = track_rows[0]['track_id']
    counts: Counter = Counter()
    with conn.cursor() as cursor, transaction(conn):
        for row in track_rows:
            counts['deleted' if _delete_if_still_gone(cursor, row) else 'changed'] += 1
        if counts['deleted'] and track_id is not None and not track_has_media_file(cursor, track_id):
            counts['left_without_file'] += 1
            target, by_name = _successor(cursor, relink, track_rows)
            moved = relink_track(cursor, track_id, target) if target is not None else None
            if moved is None:
                counts['kept_without_file'] += 1
            else:
                counts['relinked'] += 1
                counts['relinked_file_name'] += int(by_name)
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
        f"relinked to the track their file became ({totals['relinked_file_name']} by file name; ratings moved {totals['ratings_moved']}, merged "
        f"{totals['ratings_merged']}; listens moved {totals['listens_moved']}), {totals['kept_without_file']} "
        f'kept without a file for relink-orphans, {totals["failed"]} failed.'
    )
