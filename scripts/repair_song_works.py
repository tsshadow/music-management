#!/usr/bin/env python3
"""
scripts/repair_song_works.py

Detaches tracks from the work they were wrongly grouped into, so the song-versions
worker can regroup them under the corrected key.

Two faults put tracks in the wrong work, and both are fixed in code by the change that
ships this script -- but neither fix moves a row that is already wrong:

  * A title that normalizes to nothing produced the key ':::', so every title-less
    track became one song. Production had 117 unrelated recordings in work 89834
    (blank titles, a lone dove emoji, strings of combining marks) and 543 further
    tracks queued to join it.
  * `library_works.work_key` was `utf8mb4_general_ci`, in which every character
    outside the BMP has the same collation weight, so two keys of equal length built
    from such characters compared equal and the UNIQUE key merged their works.
    migrate_v19 fixes the column; the rows it already merged stay merged.

Rather than test for either fault, this recomputes the key of every unlocked track and
detaches the ones that do not match the work they sit in. That covers both, plus any
regrouping a later change to the key rules brings with it.

Detaching means `work_id`, `version_kind` and `version_score` back to NULL: the worker
picks those tracks up on its next pass -- at most an hour, see SONG_VERSION_INTERVAL --
and gives them a work under the current rules. A work left without members is deleted,
unless something still points at it. Hand-split tracks (`work_locked = 1`) are never
touched.

Read a --dry-run before running it for real. Recomputing the key also moves tracks whose
artist was renamed after they were grouped: their stored key describes a name that no
longer exists, so re-keying them is right, but it is churn rather than a repair and it
is counted separately ('stale-key') for exactly that reason.

The database connection runs with autocommit on, so this cannot hold the library still
while it works. Each statement therefore states its own precondition -- the update only
touches unlocked tracks, the delete only removes a work that is empty at the moment it
runs -- instead of trusting what was read a moment earlier.

Run it after migrate_v19_work_key_binary.sql and after the new code is deployed;
running it against the old code would only reproduce the same grouping.

Idempotent: a second run finds nothing to do.

Usage:
    python3 scripts/repair_song_works.py --dry-run
    python3 scripts/repair_song_works.py
"""

import argparse
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.music_manager.database import get_db_connection  # noqa: E402
from services.music_manager.song_version_worker import recompute_canonicals  # noqa: E402
from services.music_manager.song_versions import LONG_FORM_SECONDS, UNGROUPABLE_PREFIX, work_key  # noqa: E402

SAMPLE_SIZE = 10
UPDATE_CHUNK = 500

# Every grouped track that the worker is still allowed to move, with the key of the
# work it currently sits in. work_locked = 1 is a hand-made split and stays put.
_GROUPED = '''
    SELECT t.id, t.title, t.work_id, t.duration_secs, w.work_key, a.name AS artist
    FROM library_tracks t
    JOIN library_works w ON w.id = t.work_id
    LEFT JOIN library_artists a ON a.id = t.primary_artist_id
    WHERE t.work_locked = 0
    ORDER BY t.id
'''


# Tracks whose stored version_score was decided by the broken provenance test: a
# download that also carries a label, sitting in a work where a score can change which
# version plays. The comparison the worker used could never match SoundCloud's column,
# so these collected the "official release" bonus. Detaching them is the rescore --
# the worker gives a detached track a fresh key and a fresh score on its next pass, and
# the key is unchanged here, so they come back to the same work with the right one.
_MISSCORED_DOWNLOADS = '''
    SELECT DISTINCT t.id, t.work_id
    FROM library_tracks t
    JOIN library_media_files mf ON mf.track_id = t.id
    JOIN library_track_labels tl ON tl.track_id = t.id
    JOIN library_works w ON w.id = t.work_id
    WHERE t.work_locked = 0
      AND (
        EXISTS (SELECT 1 FROM downloads_soundcloud_archive sc WHERE sc.filename = mf.file_path)
        OR EXISTS (SELECT 1 FROM downloads_youtube_archive yt WHERE yt.path = mf.file_path)
      )
      AND (SELECT COUNT(*) FROM library_tracks m WHERE m.work_id = t.work_id) > 1
    ORDER BY t.id
'''


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Report what would be detached and write nothing.',
    )
    parser.add_argument(
        '--rescore-downloads',
        action='store_true',
        help=(
            'Also detach downloads that carry a label and share a work, so the worker '
            'scores them again with the corrected provenance test. Run once after that '
            'fix is deployed; a second run only costs the same tracks another pass.'
        ),
    )
    return parser.parse_args()


def _is_long_form(row) -> bool:
    duration = row.get('duration_secs')
    return bool(duration) and duration > LONG_FORM_SECONDS


def misfiled(rows) -> list[dict]:
    """The tracks whose current work is not the one their key asks for.

    Pure, so the rule is testable without a database. Returns the row plus the key it
    should have had and why it moves, in the order the rows came in.

    Recomputing rather than looking for the two known faults is deliberate: a work the
    collation merged carries the *other* work's key, and nothing in the row says so --
    the only evidence is that the key does not match. The same test also catches a
    track whose artist was renamed after it was grouped, whose stored key describes a
    name that no longer exists. That is reported separately, because it is a stale key
    rather than a wrong grouping, and it is the reason to read a --dry-run first.
    """
    wrong = []
    for row in rows:
        expected = work_key(row['artist'], row['title'], row['id'], row['duration_secs'])
        if expected == row['work_key']:
            continue
        if expected.startswith(UNGROUPABLE_PREFIX) and _is_long_form(row):
            # A set or a radio episode, which stopped grouping by title when
            # LONG_FORM_SECONDS arrived. Counted apart from a title that says nothing:
            # these tracks have a perfectly good title and are moving for their length.
            reason = 'long-form'
        elif expected.startswith(UNGROUPABLE_PREFIX):
            reason = 'unusable-title'
        elif row['work_key'].startswith(UNGROUPABLE_PREFIX):
            reason = 'title-became-usable'
        else:
            reason = 'stale-key'
        wrong.append({**row, 'expected_key': expected, 'reason': reason})
    return wrong


def by_reason(wrong) -> dict:
    """How many tracks move for each reason, worst first in the report."""
    counts: dict[str, int] = {}
    for row in wrong:
        counts[row['reason']] = counts.get(row['reason'], 0) + 1
    return counts


def _chunks(values, size):
    for start in range(0, len(values), size):
        yield values[start : start + size]


def detach(cursor, track_ids) -> None:
    """Put the tracks back in the worker's queue.

    `work_locked = 0` is repeated here even though the rows were read that way: the
    connection runs with autocommit on, so somebody can split a track between the read
    and this update, and clearing that split would silently undo their decision.
    """
    for chunk in _chunks(track_ids, UPDATE_CHUNK):
        placeholders = ','.join(['%s'] * len(chunk))
        cursor.execute(
            'UPDATE library_tracks SET work_id = NULL, version_kind = NULL, version_score = NULL '
            f'WHERE id IN ({placeholders}) AND work_locked = 0',
            tuple(chunk),
        )


def _is_referenced(cursor, work_id) -> bool:
    """Whether another work names this one as the original it remixes.

    related_work_id carries no foreign key in either schema definition, so nothing
    would stop the delete -- it would just leave a dangling id behind.
    """
    cursor.execute('SELECT id FROM library_works WHERE related_work_id = %s LIMIT 1', (work_id,))
    return cursor.fetchone() is not None


def settle_works(cursor, work_ids) -> dict:
    """Delete the works that lost every member, recompute the ones that kept some."""
    deleted = 0
    kept = 0
    pinned_but_empty = []

    for work_id in sorted(work_ids):
        cursor.execute('SELECT COUNT(*) AS n FROM library_tracks WHERE work_id = %s', (work_id,))
        members = cursor.fetchone()['n']

        if members:
            recompute_canonicals(cursor, {work_id})
            kept += 1
            continue

        cursor.execute('SELECT pinned_track_id FROM library_works WHERE id = %s', (work_id,))
        work = cursor.fetchone()
        if work is None:
            continue
        if work['pinned_track_id'] is not None or _is_referenced(cursor, work_id):
            # Someone chose something here, or another work points at it. Emptying it
            # is safe; removing it would throw that choice away silently.
            recompute_canonicals(cursor, {work_id})
            pinned_but_empty.append(work_id)
            continue

        # Emptiness is asserted inside the delete, not before it. The worker runs on
        # its own hourly loop against an autocommit connection, so a track can be
        # assigned to this work between the count above and this statement, and
        # deleting it then would leave that track pointing at a work that is gone.
        cursor.execute(
            'DELETE w FROM library_works w '
            'LEFT JOIN library_tracks t ON t.work_id = w.id '
            'WHERE w.id = %s AND t.id IS NULL',
            (work_id,),
        )
        deleted += cursor.rowcount or 0

    return {'works_deleted': deleted, 'works_kept': kept, 'works_emptied_not_deleted': pinned_but_empty}


def main() -> int:
    args = parse_args()

    conn = get_db_connection()
    if not conn:
        print('repair-song-works: no database connection', file=sys.stderr)
        return 1

    try:
        with conn.cursor() as cursor:
            cursor.execute(_GROUPED)
            rows = cursor.fetchall()

        wrong = misfiled(rows)
        print(f'repair-song-works: {len(rows)} grouped tracks, {len(wrong)} in the wrong work')
        for reason, count in sorted(by_reason(wrong).items(), key=lambda item: -item[1]):
            print(f'  {reason}: {count}')
        for row in wrong[:SAMPLE_SIZE]:
            print(f'  track {row["id"]} ({row["reason"]}): {row["work_key"]!r} -> {row["expected_key"]!r}')
        if len(wrong) > SAMPLE_SIZE:
            print(f'  ... and {len(wrong) - SAMPLE_SIZE} more')

        misscored = []
        if args.rescore_downloads:
            with conn.cursor() as cursor:
                cursor.execute(_MISSCORED_DOWNLOADS)
                misscored = cursor.fetchall()
            print(f'repair-song-works: {len(misscored)} labelled downloads to score again')

        # A track can be in both lists; detaching it once is enough for either reason.
        track_ids = sorted({row['id'] for row in wrong} | {row['id'] for row in misscored})
        work_ids = {row['work_id'] for row in wrong} | {row['work_id'] for row in misscored}

        if not track_ids:
            return 0

        if args.dry_run:
            print(f'repair-song-works: dry run, {len(work_ids)} works would be revisited')
            return 0
        with conn.cursor() as cursor:
            detach(cursor, track_ids)
            stats = settle_works(cursor, work_ids)
        conn.commit()

        print(
            f'repair-song-works: detached {len(track_ids)} tracks, '
            f'deleted {stats["works_deleted"]} empty works, '
            f'recomputed {stats["works_kept"]}'
        )
        if stats['works_emptied_not_deleted']:
            print(
                'repair-song-works: left in place because they are pinned or referenced: '
                + ', '.join(str(work_id) for work_id in stats['works_emptied_not_deleted'])
            )
        print('repair-song-works: the worker regroups them on its next pass')
    finally:
        conn.close()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
