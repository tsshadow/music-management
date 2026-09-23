"""Carrying a track's history over when its file moves to a different track row.

`library_tracks.track_uid` is a hash of the title, the duration and the primary artist, so a
retag that corrects a title or reorders the artists gives the same file a new track row. The
scanner then repoints the file's `library_media_files` row at the new track and, until this
module existed, left the old row behind with everything that hangs off it: the ratings
(`rating_tracks.entity_id` holds the `track_uid`) and the listens (`scrobble_listens.track_id`
holds the id) stayed on a row no file maps to any more. Nothing ever deleted such a row, and the
song-version worker could even pick it as a work's canonical, which hid the real file in LMS.

`relink_track` moves that history to the new row and deletes the old one. `relink_orphaned_tracks`
applies the same move to rows orphaned before this existed.

Deliberately not relinked: `radio_timeline.track_id` holds LMS ids, and `feeds_snapshot` is a
per-day cache the next build replaces. The junction tables (`library_track_artists`, `_genres`,
`_labels`, `_channels`) cascade with the old row; the new row's are written by the scanner from
the file itself.

Bug report: docs/bug-reports/042-retag-orphans-ratings-and-listens.md
"""

from __future__ import annotations

import logging
from datetime import datetime
from typing import Any

from services.music_manager.scrobble_matching import normalize
from services.music_manager.song_version_worker import recompute_canonicals

logger = logging.getLogger('music-manager.scanner')

#: A rating without a timestamp loses every tie: it cannot claim to be the newer one.
_NEVER = datetime.min

#: Two durations closer than this are the same recording. `duration_secs` is a FLOAT column, so
#: a value read back from MariaDB is not bit-identical to the one Python wrote.
DURATION_TOLERANCE_SECS = 0.5

_RATINGS_FOR = (
    "SELECT id, username, rating, updated_at FROM rating_tracks WHERE entity_type = 'track' AND entity_id = %s"
)

# Every track row no media file points at. A track the scanner created always has one, so a row
# without is either a retag leftover or a row ml-analyzer created and never linked.
_ORPHANS = """
    SELECT t.id, t.title, t.duration_secs, t.primary_artist_id
    FROM library_tracks t
    WHERE NOT EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id)
    ORDER BY t.id
"""

# Tracks that do have a file and could be the one an orphan became. Narrowed in SQL on duration
# and artist; the title comparison happens in Python, because `normalized_title` is filled by a
# background worker and is NULL on a row the scanner inserted minutes ago.
_CANDIDATES = """
    SELECT t.id, t.title, t.primary_artist_id
    FROM library_tracks t
    WHERE t.id <> %s
      AND ABS(t.duration_secs - %s) < %s
      AND (t.primary_artist_id = %s
           OR t.primary_artist_id IN (SELECT artist_id FROM library_track_artists WHERE track_id = %s))
      AND EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id)
"""


def empty_counts() -> dict[str, int]:
    """The counters one relink reports, all at zero."""
    return {
        'ratings_moved': 0,
        'ratings_merged': 0,
        'listens_moved': 0,
        'listens_dropped': 0,
        'tracks_deleted': 0,
    }


def track_has_media_file(cursor: Any, track_id: int) -> bool:
    """Whether any `library_media_files` row still points at this track."""
    cursor.execute('SELECT 1 AS present FROM library_media_files WHERE track_id = %s LIMIT 1', (track_id,))
    return cursor.fetchone() is not None


def relink_track(cursor: Any, old_track_id: int, new_track_id: int) -> dict[str, int] | None:
    """Move everything keyed on `old_track_id` to `new_track_id`, then delete the old row.

    Refuses -- returns None and writes nothing -- when the two are the same, when either row is
    missing, or when the old track still has a media file: then it is still a track in its own
    right, and its ratings belong to that file. The caller owns the transaction; every statement
    here runs on the one cursor so a failure half-way can be rolled back as a whole.
    """
    if old_track_id == new_track_id:
        return None
    if track_has_media_file(cursor, old_track_id):
        return None
    cursor.execute(
        'SELECT id, track_uid, work_id FROM library_tracks WHERE id IN (%s, %s)',
        (old_track_id, new_track_id),
    )
    rows = {row['id']: row for row in cursor.fetchall()}
    old, new = rows.get(old_track_id), rows.get(new_track_id)
    if old is None or new is None:
        return None

    counts = empty_counts()
    if old['track_uid'] and new['track_uid']:
        _move_ratings(cursor, old['track_uid'], new['track_uid'], counts)
    _move_listens(cursor, old_track_id, new_track_id, counts)
    _move_analysis(cursor, old, new)
    recompute = _detach_works(cursor, old_track_id, new_track_id)

    cursor.execute('DELETE FROM library_tracks WHERE id = %s', (old_track_id,))
    counts['tracks_deleted'] = 1
    if recompute:
        recompute_canonicals(cursor, recompute)
    return counts


def _move_ratings(cursor: Any, old_uid: str, new_uid: str, counts: dict[str, int]) -> None:
    """Carry each user's rating over; when both rows have one, the more recently changed wins.

    `updated_at = updated_at` on every UPDATE: the column is ON UPDATE CURRENT_TIMESTAMP, and a
    relink is not a rating change -- without it every moved rating would claim to be from today
    and win the next conflict it met.
    """
    cursor.execute(_RATINGS_FOR, (old_uid,))
    moving = cursor.fetchall()
    if not moving:
        return
    cursor.execute(_RATINGS_FOR, (new_uid,))
    staying = {row['username']: row for row in cursor.fetchall()}
    for row in moving:
        kept = staying.get(row['username'])
        if kept is None:
            cursor.execute(
                'UPDATE rating_tracks SET entity_id = %s, updated_at = updated_at WHERE id = %s',
                (new_uid, row['id']),
            )
            counts['ratings_moved'] += 1
            continue
        if (row['updated_at'] or _NEVER) > (kept['updated_at'] or _NEVER):
            cursor.execute(
                'UPDATE rating_tracks SET rating = %s, updated_at = %s WHERE id = %s',
                (row['rating'], row['updated_at'], kept['id']),
            )
        cursor.execute('DELETE FROM rating_tracks WHERE id = %s', (row['id'],))
        counts['ratings_merged'] += 1


def _move_listens(cursor: Any, old_id: int, new_id: int, counts: dict[str, int]) -> None:
    """Repoint the listens; a listen the new track already has at that moment is a duplicate.

    UPDATE IGNORE skips exactly the rows that would break UNIQUE (username, listened_at,
    track_id); whatever it left behind is that duplicate and is removed. `listened_at =
    listened_at` because the column may still carry ON UPDATE CURRENT_TIMESTAMP (bug report 039),
    and a relink must not move a listen to today.
    """
    cursor.execute(
        'UPDATE IGNORE scrobble_listens SET track_id = %s, listened_at = listened_at WHERE track_id = %s',
        (new_id, old_id),
    )
    counts['listens_moved'] += max(cursor.rowcount or 0, 0)
    cursor.execute('DELETE FROM scrobble_listens WHERE track_id = %s', (old_id,))
    counts['listens_dropped'] += max(cursor.rowcount or 0, 0)


def _move_analysis(cursor: Any, old: dict[str, Any], new: dict[str, Any]) -> None:
    """Point the ml-analyzer's rows at the new track instead of letting the FK null them.

    `library_track_ml_labels.track_id` is read by `track_uid` (library.py), so a label moves under
    the new uid too -- unless the new uid already has one, which is kept (UPDATE IGNORE).
    """
    cursor.execute(
        'UPDATE library_track_audio_features SET internal_track_id = %s WHERE internal_track_id = %s',
        (new['id'], old['id']),
    )
    cursor.execute(
        'UPDATE library_track_ml_labels SET internal_track_id = %s, updated_at = updated_at WHERE internal_track_id = %s',
        (new['id'], old['id']),
    )
    if old['track_uid'] and new['track_uid']:
        cursor.execute(
            'UPDATE IGNORE library_track_ml_labels SET track_id = %s, updated_at = updated_at WHERE track_id = %s',
            (new['track_uid'], old['track_uid']),
        )


def _detach_works(cursor: Any, old_id: int, new_id: int) -> set[int]:
    """Take the old track out of every work that names it; return the works to recompute now.

    A pin follows the file to the new track and the canonical is cleared, which is exactly the
    state the song-version worker's next pass picks up: it assigns the new track a work first and
    then recomputes every work whose pin differs from its canonical, so the pin survives when the
    new track joins the same song and is dropped when it does not. A work that merely had the old
    track as its computed canonical is recomputed here, so it never spends an hour without one.
    """
    cursor.execute(
        'SELECT id, pinned_track_id FROM library_works WHERE canonical_track_id = %s OR pinned_track_id = %s',
        (old_id, old_id),
    )
    works = cursor.fetchall()
    if not works:
        return set()
    cursor.execute('UPDATE library_works SET pinned_track_id = %s WHERE pinned_track_id = %s', (new_id, old_id))
    cursor.execute('UPDATE library_works SET canonical_track_id = NULL WHERE canonical_track_id = %s', (old_id,))
    return {int(work['id']) for work in works if work['pinned_track_id'] != old_id}


def find_relink_target(cursor: Any, orphan: dict[str, Any]) -> int | None:
    """The one track with a file that this orphan became, or None when there is not exactly one.

    Same normalised title, same duration, and the same primary artist -- or, for a retag that only
    reordered the credits, the same set of artists in another order. Two candidates is a
    duplicate recording and one is not guessed at.
    """
    if orphan.get('duration_secs') is None or orphan.get('primary_artist_id') is None:
        return None
    title = normalize(orphan.get('title'))
    if not title:
        return None
    cursor.execute(
        _CANDIDATES,
        (
            orphan['id'],
            orphan['duration_secs'],
            DURATION_TOLERANCE_SECS,
            orphan['primary_artist_id'],
            orphan['id'],
        ),
    )
    candidates = [row for row in cursor.fetchall() if normalize(row['title']) == title]
    if not candidates:
        return None
    orphan_artists: set[int] | None = None
    matches = []
    for row in candidates:
        if row['primary_artist_id'] == orphan['primary_artist_id']:
            matches.append(int(row['id']))
            continue
        if orphan_artists is None:
            orphan_artists = _artist_set(cursor, orphan['id'])
        if orphan_artists and _artist_set(cursor, row['id']) == orphan_artists:
            matches.append(int(row['id']))
    return matches[0] if len(matches) == 1 else None


def _artist_set(cursor: Any, track_id: int) -> set[int]:
    """Every artist credited on a track, regardless of role or position."""
    cursor.execute('SELECT artist_id FROM library_track_artists WHERE track_id = %s', (track_id,))
    return {int(row['artist_id']) for row in cursor.fetchall()}


def relink_orphaned_tracks(conn: Any) -> dict[str, int]:
    """Relink every fileless track that has exactly one successor; report what happened.

    Takes the connection rather than a cursor because each orphan is its own transaction: one
    that fails is rolled back and counted, and the rest still go through. Idempotent -- a relinked
    orphan is deleted, so a second run finds only the ones it could not match.
    """
    totals = empty_counts() | {'orphans': 0, 'relinked': 0, 'unmatched': 0, 'failed': 0}
    with conn.cursor() as cursor:
        cursor.execute(_ORPHANS)
        orphans = cursor.fetchall()
    for orphan in orphans:
        totals['orphans'] += 1
        with conn.cursor() as cursor:
            target = find_relink_target(cursor, orphan)
            if target is None:
                totals['unmatched'] += 1
                continue
            conn.begin()
            try:
                counts = relink_track(cursor, orphan['id'], target)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                totals['failed'] += 1
                logger.warning('Relinking orphaned track %s to %s failed: %s', orphan['id'], target, exc)
                continue
        if counts is None:
            totals['unmatched'] += 1
            continue
        totals['relinked'] += 1
        for key, value in counts.items():
            totals[key] += value
    return totals
