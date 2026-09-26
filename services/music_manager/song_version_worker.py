"""Grouping every track under a song, and choosing which one plays.

The rules live in song_versions.py; this module owns the SQL.

Deliberately a worker rather than a step in process_file(): tracks are inserted
from the scanner and the ml-analyzer today and from somewhere else tomorrow, and
a grouping that hangs off one writer misses the rest in silence. Same reasoning
as backfill_normalized() in scrobble_rematch.py.

Design: docs/superpowers/specs/2026-08-23-song-versions-and-canonical-design.md, and for the
ranking and the rescore docs/designs/song-versions/.
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
from dataclasses import dataclass

from services.common.config_store import ConfigStore
from services.common.import_queue import ImportQueue
from services.music_manager.database import get_db_connection
from services.music_manager.song_versions import (
    SPLIT_PREFIX,
    derived_bitrate,
    is_official_release,
    ranking_signature,
    version_kind,
    version_score,
    work_key,
)
from services.music_manager.song_work_audit import AUTO_SPLIT_LENGTHS, assess_work, suspicious_works
from services.music_manager.thread_registry import run_forever

logger = logging.getLogger('music-manager.song-versions')

BATCH_SIZE = int(os.getenv('SONG_VERSION_BATCH', '500'))
INTERVAL_SECONDS = int(os.getenv('SONG_VERSION_INTERVAL', '3600'))
# Works per rescore batch. Each batch is one read of its members and one commit.
RESCORE_BATCH = int(os.getenv('SONG_VERSION_RESCORE_BATCH', '500'))

# One row per file of the tracks that still need a work, carrying everything the
# ranking asks for. The label join and the two download archives feed the
# official-release tier together with the file's place in the label tree
# (song_versions.is_official_release).
#
# The batch is picked in a derived table, before the media-file join, because LIMIT
# counts joined rows. Limiting the joined result cut the last track of a batch off
# from its remaining files, and since that track came out of the pass with a work it
# never returned -- so a track was scored on whichever of its files happened to fall
# inside the limit, and its FLAC could lose to its own MP3.
_UNGROUPED = '''
    SELECT
        t.id,
        t.title,
        a.name AS artist,
        mf.file_path,
        mf.file_size,
        COALESCE(mf.duration_secs, t.duration_secs) AS duration_secs,
        EXISTS (SELECT 1 FROM library_track_labels tl WHERE tl.track_id = t.id) AS has_label,
        -- Matched on the absolute path, which is what both archives store: SoundCloud
        -- writes it into `filename` and YouTube into `path`. Comparing a basename
        -- against SoundCloud's column could never be true -- all 157.393 rows hold a
        -- path beginning with a slash -- so every SoundCloud rip read as "not from
        -- SoundCloud" and the 1.162 of them carrying a label collected the provenance
        -- bonus meant for an official release. That is the exact inversion this
        -- scoring exists to remove. Indexed by migrate_v23.
        EXISTS (
            SELECT 1 FROM downloads_soundcloud_archive sc
            WHERE sc.filename = mf.file_path
        ) AS from_soundcloud,
        EXISTS (
            SELECT 1 FROM downloads_youtube_archive yt
            WHERE yt.path = mf.file_path
        ) AS from_youtube
    FROM (
        SELECT id FROM library_tracks
        WHERE work_id IS NULL AND work_locked = 0
        ORDER BY id
        LIMIT %s
    ) AS batch
    JOIN library_tracks t ON t.id = batch.id
    LEFT JOIN library_artists a ON a.id = t.primary_artist_id
    LEFT JOIN library_media_files mf ON mf.track_id = t.id
    ORDER BY t.id
'''

# Highest score wins; the two tie-breaks keep the choice stable between passes so
# the canonical does not move on its own.
#
# Only a track with a file can win. With a LEFT JOIN a row no file maps to any more
# -- a retag leftover, see track_relink.py -- tied with the real file on score and
# won on `created_at ASC` for being older, and song_version_sync then marked the
# real file non-canonical in LMS. A work whose tracks all lost their files gets no
# canonical, which LMS reads as "every version is canonical".
_BEST_TRACK = '''
    SELECT t.id
    FROM library_tracks t
    JOIN library_media_files mf ON mf.track_id = t.id
    WHERE t.work_id = %s
    ORDER BY t.version_score DESC,
             (mf.file_size / NULLIF(mf.duration_secs, 0)) DESC,
             t.created_at ASC,
             t.id ASC
    LIMIT 1
'''


@dataclass(frozen=True)
class RankingContext:
    """Everything the ranking reads besides the row itself.

    Read once per pass rather than per row: the setting and the label tree cannot change
    meaningfully in the middle of a batch, and a pass that mixed two settings would store
    scores that compare nothing.
    """

    prefer_lossless: bool = True
    label_tree_roots: tuple[str, ...] = ()

    @property
    def signature(self) -> str:
        """The ranking signature scores computed under this context carry."""
        return ranking_signature(self.prefer_lossless)


def ranking_context(settings=None) -> RankingContext:
    """The context as configured: `prefer_lossless` and the label tree with the import queue.

    The queue is named separately because it may live outside `eps_folder_path` after the
    move described in services/common/import_queue.py; a release waiting there is an
    official release that simply has no label yet.
    """
    if settings is None:
        settings = ConfigStore()
    prefer = getattr(settings, 'prefer_lossless', True)
    roots: list[str] = []
    eps_root = getattr(settings, 'eps_folder_path', '')
    if isinstance(eps_root, str) and eps_root.strip():
        roots.append(os.path.normpath(eps_root.strip()))
    queue = ImportQueue.from_settings(settings).path
    if queue and not any(queue.startswith(root.rstrip('/') + '/') for root in roots):
        roots.append(queue)
    return RankingContext(prefer_lossless=prefer is not False, label_tree_roots=tuple(roots))


def _rank_row(row, context: RankingContext | None = None) -> tuple[str, int]:
    """The kind and packed score for one candidate row."""
    context = context or RankingContext()
    kind = version_kind(row['title'])
    official = is_official_release(
        row['file_path'],
        bool(row['has_label']),
        bool(row['from_soundcloud'] or row['from_youtube']),
        context.label_tree_roots,
    )
    bitrate = derived_bitrate(row['file_size'], row['duration_secs'])
    score = version_score(
        kind,
        row['file_path'] or '',
        bitrate,
        is_official=official,
        prefer_lossless=context.prefer_lossless,
    )
    return kind, score


def _best_per_track(rows, context: RankingContext | None = None) -> dict[int, dict]:
    """One entry per track, scored on its best file.

    A track can own several files -- the FLAC and the MP3 of one release -- so the
    join returns it once per file. The spec ranks a track on its best one, and
    without this the last row seen would win instead of the best.
    """
    best: dict[int, dict] = {}
    for row in rows:
        kind, score = _rank_row(row, context)
        current = best.get(row['id'])
        if current is None or score > current['score']:
            best[row['id']] = {'row': row, 'kind': kind, 'score': score}
    return best


def assign_works(cursor, limit: int = BATCH_SIZE, context: RankingContext | None = None) -> tuple[set[int], int]:
    """Give every ungrouped track a work, a kind and a score.

    Returns the work ids that were touched and how many tracks were assigned. The
    limit counts tracks: the batch is chosen before the media-file join, so every
    file of every track in it is present and the ranking sees all of them.

    A work created here is stamped with the current ranking signature, because every
    track in it was just scored under that ranking. A work that already existed keeps
    its signature: its older tracks may still carry an older score, and only the
    rescore is allowed to say otherwise.
    """
    context = context or RankingContext()
    cursor.execute(_UNGROUPED, (limit,))
    rows = cursor.fetchall()

    touched: set[int] = set()
    candidates = _best_per_track(rows, context)
    for track_id, candidate in candidates.items():
        row = candidate['row']
        key = work_key(row['artist'], row['title'], track_id, row['duration_secs'])
        cursor.execute(
            'INSERT INTO library_works (work_key, title, primary_artist_id, ranking_signature) '
            'VALUES (%s, %s, (SELECT primary_artist_id FROM library_tracks WHERE id = %s), %s) '
            'ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)',
            (key, row['title'], track_id, context.signature),
        )
        cursor.execute('SELECT id FROM library_works WHERE work_key = %s', (key,))
        work_id = cursor.fetchone()['id']

        cursor.execute(
            'UPDATE library_tracks SET work_id = %s, version_kind = %s, version_score = %s WHERE id = %s',
            (work_id, candidate['kind'], candidate['score'], track_id),
        )
        touched.add(work_id)

    return touched, len(candidates)


def recompute_canonicals(cursor, work_ids: set[int]) -> int:
    """Set canonical_track_id for each work. A pin wins; otherwise the best score does."""
    for work_id in work_ids:
        cursor.execute('SELECT pinned_track_id FROM library_works WHERE id = %s', (work_id,))
        row = cursor.fetchone()
        if row is None:
            continue

        canonical = row['pinned_track_id']
        if canonical is not None:
            # A pin only decides while the track it names is still a member. Splitting
            # a pinned track moves it to a work of its own and leaves the pin behind,
            # and following it would make this work canonical-point at a track that
            # now belongs to another song.
            cursor.execute(
                'SELECT id FROM library_tracks WHERE id = %s AND work_id = %s',
                (canonical, work_id),
            )
            if cursor.fetchone() is None:
                cursor.execute(
                    'UPDATE library_works SET pinned_track_id = NULL WHERE id = %s',
                    (work_id,),
                )
                canonical = None

        if canonical is None:
            cursor.execute(_BEST_TRACK, (work_id,))
            best = cursor.fetchone()
            canonical = best['id'] if best else None

        cursor.execute(
            'UPDATE library_works SET canonical_track_id = %s WHERE id = %s',
            (canonical, work_id),
        )
    return len(work_ids)


# Members of every work large enough to be worth assessing, for the false-merge report.
_ASSESSABLE_MEMBERS = '''
    SELECT t.work_id, w.work_key, t.id, t.duration_secs, t.release_date, t.work_locked
    FROM library_tracks t
    JOIN library_works w ON w.id = t.work_id
    WHERE t.work_id IN (
        SELECT work_id FROM (
            SELECT work_id FROM library_tracks
            WHERE work_id IS NOT NULL
            GROUP BY work_id
            HAVING COUNT(*) >= %s
        ) AS big
    )
    ORDER BY t.work_id, t.id
'''


# Every work with more members than the split threshold -- the only works that can have
# more different lengths than that.
_LARGE_WORKS = '''
    SELECT work_id FROM library_tracks
    WHERE work_id IS NOT NULL
    GROUP BY work_id
    HAVING COUNT(*) > %s
'''


def find_suspicious_works(cursor, min_members: int = 4) -> list[dict]:
    """Every work that looks like several songs, worst first (song_work_audit.assess_work)."""
    cursor.execute(_ASSESSABLE_MEMBERS, (min_members,))
    return suspicious_works(cursor.fetchall())


def split_work(cursor, work_id: int) -> list[int]:
    """Give every unlocked member of a work a work of its own, locked there.

    The same move the split endpoint in routers/songs.py makes for one track: a `split:`
    key that cannot collide with a real one, and `work_locked = 1` so neither this worker
    nor scripts/repair_song_works.py puts the track back. Each statement states its own
    precondition -- the track is still in this work and still unlocked -- because the
    connection runs with autocommit on. Returns the ids of the tracks that moved.
    """
    cursor.execute(
        'SELECT id, title, primary_artist_id FROM library_tracks WHERE work_id = %s AND work_locked = 0 ORDER BY id',
        (work_id,),
    )
    members = cursor.fetchall()

    moved: list[int] = []
    new_works: set[int] = set()
    for member in members:
        key = f'{SPLIT_PREFIX}{member["id"]}'
        cursor.execute(
            'INSERT INTO library_works (work_key, title, primary_artist_id) VALUES (%s, %s, %s) '
            'ON DUPLICATE KEY UPDATE id = LAST_INSERT_ID(id)',
            (key, member['title'], member['primary_artist_id']),
        )
        cursor.execute('SELECT id FROM library_works WHERE work_key = %s', (key,))
        new_work = cursor.fetchone()
        if new_work is None:
            continue
        cursor.execute(
            'UPDATE library_tracks SET work_id = %s, work_locked = 1 WHERE id = %s AND work_id = %s AND work_locked = 0',
            (new_work['id'], member['id'], work_id),
        )
        if cursor.rowcount:
            moved.append(member['id'])
            new_works.add(new_work['id'])

    if moved:
        # recompute_canonicals also clears the old work's pin when it named one of the
        # tracks that just left -- the same rule a manual split relies on.
        recompute_canonicals(cursor, new_works | {work_id})
    return moved


def split_false_merges(cursor, work_ids) -> dict[int, list[int]]:
    """Split the works among `work_ids` that the unambiguous rule says hold several songs.

    Only a work with more than AUTO_SPLIT_LENGTHS members can have that many different
    lengths, so one indexed count over library_tracks finds every such work before any
    member is read; the few it returns are intersected with `work_ids`. A single literal
    statement rather than an IN list over the touched works: nothing is formatted into the
    SQL. Returns {work_id: moved track ids} for the works that were split.
    """
    work_ids = set(work_ids)
    if not work_ids:
        return {}
    cursor.execute(_LARGE_WORKS, (AUTO_SPLIT_LENGTHS,))
    candidates = sorted(row['work_id'] for row in cursor.fetchall() if row['work_id'] in work_ids)

    split: dict[int, list[int]] = {}
    for work_id in candidates:
        cursor.execute('SELECT duration_secs, release_date FROM library_tracks WHERE work_id = %s', (work_id,))
        verdict = assess_work(cursor.fetchall())
        if verdict and verdict['verdict'] == 'split':
            moved = split_work(cursor, work_id)
            if moved:
                split[work_id] = moved
                logger.info(
                    'song-versions: split work %d (%d different lengths) into %d works',
                    work_id,
                    verdict['lengths'],
                    len(moved),
                )
    return split


def group_once(conn, context: RankingContext | None = None) -> dict:
    """One pass. Idempotent: a second call over unchanged data writes nothing new."""
    with conn.cursor() as cursor:
        touched, assigned = assign_works(cursor, context=context)

        # Works whose pin moved need recomputing even when no track was assigned.
        cursor.execute(
            'SELECT id FROM library_works '
            'WHERE pinned_track_id IS NOT NULL AND pinned_track_id <> COALESCE(canonical_track_id, 0)'
        )
        touched.update(row['id'] for row in cursor.fetchall())

        # A work that grew into a series of different songs is split before its canonical
        # is chosen (bug report 098, song_work_audit.AUTO_SPLIT_LENGTHS).
        split_false_merges(cursor, touched)

        recomputed = recompute_canonicals(cursor, touched)

        cursor.execute('SELECT COUNT(*) AS n FROM library_tracks WHERE work_id IS NULL AND work_locked = 0')
        remaining = cursor.fetchone()['n']
    conn.commit()
    return {'assigned': assigned, 'remaining': remaining, 'recomputed': recomputed}


# --- Rescoring -------------------------------------------------------------------------
#
# A stored score is never refreshed by the grouping pass above, which only looks at tracks
# without a work. So a change to the ranking -- a new RANKING_VERSION, or the
# prefer_lossless setting flipped in Beheer -- would otherwise reach only the tracks
# scanned after it. The rescore walks every work whose `ranking_signature` differs from the
# current one, in batches by work id, recomputes each member's kind and score and the
# work's canonical, and stamps the batch with the new signature. It never regroups:
# work_id is read, not written.
#
# Idempotent by construction: a rescored work carries the current signature and is not
# selected again, and a batch that finds nothing different writes nothing but the stamp.
# Resumable for the same reason -- a restart halfway picks up at the first work still
# carrying the old signature.

_RESCORE_WORKS = '''
    SELECT id, canonical_track_id, pinned_track_id
    FROM library_works
    WHERE (ranking_signature IS NULL OR ranking_signature <> %s) AND id > %s
    ORDER BY id
    LIMIT %s
'''

# Same columns as _UNGROUPED, for the members of a batch of works instead of the tracks
# without one, plus what the canonical choice needs.
#
# The batch is addressed as "the works between its first and last id that still carry
# another signature" rather than as an IN list: _RESCORE_WORKS returned exactly the first
# BATCH works with a differing signature above the cursor, so every such work in that id
# range is in the batch and no other is. That keeps the statement fixed text -- no
# placeholder list formatted into it.
_RESCORE_TRACKS = '''
    SELECT
        t.id,
        t.work_id,
        t.title,
        t.version_kind,
        t.version_score,
        t.created_at,
        mf.file_path,
        mf.file_size,
        COALESCE(mf.duration_secs, t.duration_secs) AS duration_secs,
        EXISTS (SELECT 1 FROM library_track_labels tl WHERE tl.track_id = t.id) AS has_label,
        EXISTS (
            SELECT 1 FROM downloads_soundcloud_archive sc
            WHERE sc.filename = mf.file_path
        ) AS from_soundcloud,
        EXISTS (
            SELECT 1 FROM downloads_youtube_archive yt
            WHERE yt.path = mf.file_path
        ) AS from_youtube
    FROM library_tracks t
    JOIN library_works w ON w.id = t.work_id
    LEFT JOIN library_media_files mf ON mf.track_id = t.id
    WHERE t.work_id BETWEEN %s AND %s
      AND (w.ranking_signature IS NULL OR w.ranking_signature <> %s)
    ORDER BY t.id
'''

_STAMP_BATCH = '''
    UPDATE library_works SET ranking_signature = %s
    WHERE id BETWEEN %s AND %s
      AND (ranking_signature IS NULL OR ranking_signature <> %s)
'''


def _file_ratio(row) -> float:
    """`file_size / duration_secs`, the SQL tie-break; -1 where MariaDB would sort NULL last."""
    size, duration = row.get('file_size'), row.get('duration_secs')
    if size is None or not duration:
        return -1.0
    return float(size) / float(duration)


def best_track(rows, scores: dict[int, int]) -> int | None:
    """The automatic canonical among `rows` (one per file), mirroring _BEST_TRACK.

    Only a row with a file can win, then: highest score, highest size-per-second, oldest,
    lowest id. Kept in step with _BEST_TRACK by RescoreTest, because the two decide the same
    thing -- the SQL for a single work after a pin, this for a whole batch at once.
    """
    candidates = [row for row in rows if row.get('file_path')]
    if not candidates:
        return None

    def order(row):
        created = row.get('created_at')
        created_key = created.timestamp() if hasattr(created, 'timestamp') else 0.0
        return (-scores[row['id']], -_file_ratio(row), created_key, row['id'])

    return min(candidates, key=order)['id']


def rescore_batch(cursor, works: list[dict], context: RankingContext, *, dry_run: bool = False) -> dict:
    """Rescore one batch of works. Returns counts; writes nothing when `dry_run`.

    `works` is one result of _RESCORE_WORKS, in ascending id order: the batch is addressed by
    its id range (see _RESCORE_TRACKS).
    """
    first, last = works[0]['id'], works[-1]['id']
    cursor.execute(_RESCORE_TRACKS, (first, last, context.signature))
    rows = cursor.fetchall()

    by_work: dict[int, list[dict]] = {}
    for row in rows:
        by_work.setdefault(row['work_id'], []).append(row)

    best = _best_per_track(rows, context)
    scores = {track_id: candidate['score'] for track_id, candidate in best.items()}
    track_updates = [
        (candidate['kind'], candidate['score'], track_id)
        for track_id, candidate in best.items()
        if candidate['row']['version_kind'] != candidate['kind']
        or candidate['row']['version_score'] != candidate['score']
    ]

    changed: list[tuple[int, int | None, int | None]] = []  # (work, old, new)
    pins_cleared: list[int] = []
    for work in works:
        members = by_work.get(work['id'], [])
        member_ids = {row['id'] for row in members}
        pinned = work['pinned_track_id']
        if pinned is not None and pinned in member_ids:
            canonical = pinned
        else:
            if pinned is not None:
                pins_cleared.append(work['id'])
            canonical = best_track(members, scores)
        if canonical != work['canonical_track_id']:
            changed.append((work['id'], work['canonical_track_id'], canonical))

    if not dry_run:
        if track_updates:
            cursor.executemany(
                'UPDATE library_tracks SET version_kind = %s, version_score = %s WHERE id = %s',
                track_updates,
            )
        for work_id in pins_cleared:
            cursor.execute('UPDATE library_works SET pinned_track_id = NULL WHERE id = %s', (work_id,))
        for work_id, old, new in changed:
            if old is None or new is None:
                # A work that had no canonical yet gained one, or a work none of whose tracks
                # has a file any more lost it (only a playable track can win). Neither
                # replaced one playable version with another, so there is nothing for a
                # curator to review -- flagging the second kind put 77k works with no file
                # on the Versies page's "changed" list on 2026-09-26 (bug report 100).
                cursor.execute(
                    'UPDATE library_works SET canonical_track_id = %s WHERE id = %s',
                    (new, work_id),
                )
            else:
                # Remember what it was: the Versies page flags these works so a curator
                # can see what the new ranking changed and pin the old choice back.
                cursor.execute(
                    'UPDATE library_works SET canonical_track_id = %s, previous_canonical_track_id = %s, '
                    'canonical_changed_at = CURRENT_TIMESTAMP WHERE id = %s',
                    (new, old, work_id),
                )
        cursor.execute(_STAMP_BATCH, (context.signature, first, last, context.signature))

    return {
        'works': len(works),
        'tracks_rescored': len(track_updates),
        'canonicals_changed': sum(1 for _work, old, new in changed if old is not None and new is not None),
    }


def rescore_once(
    conn, context: RankingContext | None = None, *, dry_run: bool = False, batch_size: int = RESCORE_BATCH
) -> dict:
    """Rescore every work whose signature differs from the current ranking's.

    Commits per batch, so a long run holds no lock for long and a restart loses at most one
    batch. With `dry_run` it walks the same works and counts what would change, writing
    nothing -- which is how the worker measures a new ranking before applying it.
    """
    context = context or ranking_context()
    totals = {'works': 0, 'tracks_rescored': 0, 'canonicals_changed': 0}
    last_id = 0
    while True:
        with conn.cursor() as cursor:
            cursor.execute(_RESCORE_WORKS, (context.signature, last_id, batch_size))
            works = cursor.fetchall()
            if not works:
                break
            stats = rescore_batch(cursor, works, context, dry_run=dry_run)
        if not dry_run:
            conn.commit()
        for key in totals:
            totals[key] += stats[key]
        last_id = works[-1]['id']
    return totals


def rescore_pending(conn, context: RankingContext) -> bool:
    """Whether any work still carries a signature other than the current one."""
    with conn.cursor() as cursor:
        cursor.execute(
            'SELECT 1 AS pending FROM library_works WHERE ranking_signature IS NULL OR ranking_signature <> %s LIMIT 1',
            (context.signature,),
        )
        return cursor.fetchone() is not None


def rescore_tick(conn, context: RankingContext) -> dict | None:
    """Measure, then apply, a rescore when the ranking changed. None when nothing was pending.

    The dry run first is deliberate: the log then says how many canonicals the new ranking
    is about to move before a single one moves, which is the number worth knowing if the
    result looks wrong afterwards.
    """
    if not rescore_pending(conn, context):
        return None
    preview = rescore_once(conn, context, dry_run=True)
    logger.info(
        'song-versions: ranking %s will rescore %d works and change %d canonicals',
        context.signature,
        preview['works'],
        preview['canonicals_changed'],
    )
    applied = rescore_once(conn, context)
    logger.info(
        'song-versions: ranking %s applied: %d works, %d tracks rescored, %d canonicals changed',
        context.signature,
        applied['works'],
        applied['tracks_rescored'],
        applied['canonicals_changed'],
    )
    return applied


def grouping_tick() -> None:
    """One grouping pass, then a rescore if the ranking changed; raises on a database failure."""
    conn = get_db_connection()
    if not conn:
        return
    try:
        context = ranking_context()
        stats = group_once(conn, context)
        if stats['recomputed']:
            logger.info('song-versions: recomputed %d works', stats['recomputed'])
        rescore_tick(conn, context)
    finally:
        conn.close()


def run_song_version_grouping() -> None:
    """The `song-versions` thread: a pass every INTERVAL_SECONDS, a failure waits the same."""
    run_forever('song-versions', grouping_tick, INTERVAL_SECONDS, backoff=False)


def main(argv: list[str] | None = None) -> int:
    """`python -m services.music_manager.song_version_worker --rescore-dry-run`: count, write nothing."""
    parser = argparse.ArgumentParser(description=main.__doc__)
    parser.add_argument('--rescore-dry-run', action='store_true', help='count what a rescore would change')
    args = parser.parse_args(argv)
    if not args.rescore_dry_run:
        parser.print_help()
        return 2
    conn = get_db_connection()
    if not conn:
        print('song-versions: no database connection', file=sys.stderr)
        return 1
    try:
        context = ranking_context()
        stats = rescore_once(conn, context, dry_run=True)
    finally:
        conn.close()
    print(json.dumps({'signature': context.signature, **stats}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
