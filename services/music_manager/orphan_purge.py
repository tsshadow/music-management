"""Deleting the fileless track rows that nothing a user made refers to (bug report 104).

`track_relink.relink_orphaned_tracks` moves an orphan's history to its successor when one of its
keys finds exactly one. What is left after it has no successor anyone can name: on production
2026-09-26 that was tens of thousands of rows, almost all of them a first-scan stub or a retag
leftover with no listen, no rating and no pin -- nothing a person would miss, yet each one still
counts as a track in every query that forgets to join `library_media_files`, and each can be
dragged into a work by the song-version worker.

`purge_orphaned_tracks` deletes exactly those. An orphan is kept, and reported with its counts for
a person to decide, when anything a user made points at it:

- a listen (`scrobble_listens.track_id` is the id; the FK would cascade the listen away);
- a rating (`rating_tracks.entity_id` is the `track_uid`, entity_type 'track');
- a work pin (`library_works.pinned_track_id`) -- a curator's choice;
- a reviewed ml label (`library_track_ml_labels` keyed on the `track_uid` with a review status
  other than 'unreviewed', or approved for training) -- a curator's verdict.

What a purged orphan takes with it, in the same batch transaction: its artist, genre, label and
channel links (they would cascade anyway; deleting them first makes the count visible), its
unreviewed ml labels (keyed on the `track_uid`, so no FK reaches them and they would dangle), and
any `canonical_track_id` / `previous_canonical_track_id` naming it (cleared; a work that lost its
canonical is recomputed at once, the same as `track_relink._detach_works`). The ml-analyzer's
`internal_track_id` columns are nulled, which is what their ON DELETE SET NULL does too.

Deliberately untouched: `radio_timeline.track_id` holds LMS ids, not ours;
`downloads_soundcloud_unavailable.track_id` is a SoundCloud id; `library_track_ml_predictions`
keys on a file hash or a stringified id and is empty on production (the ml-analyzer is
deprecated).

Batched: 1000 orphans per transaction, so no statement holds a lock for long while the API, the
tagger and the scanner share the database. Every guard is repeated inside the batch, in SQL, with
the rows locked, so a listen or a file that arrived since the survey keeps its track.
"""

from __future__ import annotations

import logging
from typing import Any

from services.music_manager.song_version_worker import recompute_canonicals

logger = logging.getLogger('music-manager.scanner')

PURGE_BATCH = 1000

#: How many kept orphans a run lists by name; the rest are only counted.
KEPT_LIST_LIMIT = 1000

_ORPHANS = """
    SELECT t.id, t.track_uid, t.title
    FROM library_tracks t
    WHERE NOT EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id)
    ORDER BY t.id
"""

# The references, read once per run as sets rather than joined per orphan:
# library_works.pinned_track_id has no index, and a correlated subquery on it per orphan is a
# full scan of library_works 80,000 times.
_LISTENED = 'SELECT track_id, COUNT(*) AS n FROM scrobble_listens WHERE track_id IS NOT NULL GROUP BY track_id'
_RATED = "SELECT entity_id, COUNT(*) AS n FROM rating_tracks WHERE entity_type = 'track' GROUP BY entity_id"
_PINNED = 'SELECT pinned_track_id AS track_id FROM library_works WHERE pinned_track_id IS NOT NULL'

# A label a curator looked at. NULL status reads as the column default, 'unreviewed'. Written
# without a table alias, so the same text serves the single-table DELETE below.
_REVIEWED_CONDITION = (
    "(COALESCE(ml_review_status, 'unreviewed') <> 'unreviewed' OR COALESCE(approved_for_training, 0) <> 0)"
)
_REVIEWED = f'SELECT track_id, COUNT(*) AS n FROM library_track_ml_labels WHERE {_REVIEWED_CONDITION} GROUP BY track_id'

# Inside the batch: which of the planned ids are still unreferenced orphans, locked until COMMIT.
_CONFIRM = f"""
    SELECT t.id, t.track_uid
    FROM library_tracks t
    WHERE t.id IN ({{ids}})
      AND NOT EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id)
      AND NOT EXISTS (SELECT 1 FROM scrobble_listens s WHERE s.track_id = t.id)
      AND NOT EXISTS (SELECT 1 FROM rating_tracks r WHERE r.entity_type = 'track' AND r.entity_id = t.track_uid)
      AND t.id NOT IN (SELECT w.pinned_track_id FROM library_works w WHERE w.pinned_track_id IS NOT NULL)
      AND NOT EXISTS (SELECT 1 FROM library_track_ml_labels l WHERE l.track_id = t.track_uid AND {_REVIEWED_CONDITION})
    FOR UPDATE
"""

#: The link tables that key on library_tracks.id and go with the track.
LINK_TABLES = ('library_track_artists', 'library_track_genres', 'library_track_labels', 'library_track_channels')


def empty_purge_totals(dry_run: bool = False) -> dict[str, Any]:
    """The totals one purge run reports, all at zero."""
    return {
        'orphans': 0,
        'purged': 0,
        'kept': 0,
        'kept_listens': 0,
        'kept_ratings': 0,
        'kept_pinned': 0,
        'kept_reviewed_labels': 0,
        'skipped_changed': 0,
        'failed_batches': 0,
        'links_deleted': 0,
        'ml_labels_deleted': 0,
        'works_cleared': 0,
        'dry_run': dry_run,
    }


def survey_orphans(cursor: Any) -> tuple[list[int], list[dict[str, Any]]]:
    """Split the current orphans into the ids to purge and the kept ones with their counts."""
    cursor.execute(_LISTENED)
    listens = {int(row['track_id']): int(row['n']) for row in cursor.fetchall()}
    cursor.execute(_RATED)
    ratings = {row['entity_id']: int(row['n']) for row in cursor.fetchall()}
    cursor.execute(_PINNED)
    pinned = {int(row['track_id']) for row in cursor.fetchall()}
    cursor.execute(_REVIEWED)
    reviewed = {row['track_id']: int(row['n']) for row in cursor.fetchall()}
    cursor.execute(_ORPHANS)
    purge: list[int] = []
    kept: list[dict[str, Any]] = []
    for row in cursor.fetchall():
        track_id, uid = int(row['id']), row['track_uid']
        refs = {
            'listens': listens.get(track_id, 0),
            'ratings': ratings.get(uid, 0) if uid else 0,
            'pinned': 1 if track_id in pinned else 0,
            'reviewed_labels': reviewed.get(uid, 0) if uid else 0,
        }
        if any(refs.values()):
            kept.append({'id': track_id, 'title': row['title']} | refs)
        else:
            purge.append(track_id)
    return purge, kept


def purge_batch(cursor: Any, ids: list[int]) -> dict[str, int]:
    """Delete the orphans among `ids` that are still unreferenced; the caller owns the transaction."""
    counts = {'purged': 0, 'links_deleted': 0, 'ml_labels_deleted': 0, 'works_cleared': 0}
    if not ids:
        return counts
    cursor.execute(_CONFIRM.format(ids=', '.join(['%s'] * len(ids))), tuple(ids))
    rows = cursor.fetchall()
    if not rows:
        return counts
    confirmed = [int(row['id']) for row in rows]
    uids = [row['track_uid'] for row in rows if row['track_uid']]
    marks = ', '.join(['%s'] * len(confirmed))
    params = tuple(confirmed)

    cursor.execute(f'SELECT id FROM library_works WHERE canonical_track_id IN ({marks})', params)
    recompute = {int(row['id']) for row in cursor.fetchall()}
    cursor.execute(f'UPDATE library_works SET canonical_track_id = NULL WHERE canonical_track_id IN ({marks})', params)
    counts['works_cleared'] += max(cursor.rowcount or 0, 0)
    cursor.execute(
        f'UPDATE library_works SET previous_canonical_track_id = NULL WHERE previous_canonical_track_id IN ({marks})',
        params,
    )
    counts['works_cleared'] += max(cursor.rowcount or 0, 0)
    for table in LINK_TABLES:
        cursor.execute(f'DELETE FROM {table} WHERE track_id IN ({marks})', params)
        counts['links_deleted'] += max(cursor.rowcount or 0, 0)
    cursor.execute(
        f'UPDATE library_track_audio_features SET internal_track_id = NULL WHERE internal_track_id IN ({marks})',
        params,
    )
    cursor.execute(
        'UPDATE library_track_ml_labels SET internal_track_id = NULL, updated_at = updated_at '
        f'WHERE internal_track_id IN ({marks})',
        params,
    )
    if uids:
        cursor.execute(
            f'DELETE FROM library_track_ml_labels WHERE track_id IN ({", ".join(["%s"] * len(uids))}) '
            f'AND NOT {_REVIEWED_CONDITION}',
            tuple(uids),
        )
        counts['ml_labels_deleted'] += max(cursor.rowcount or 0, 0)
    cursor.execute(f'DELETE FROM library_tracks WHERE id IN ({marks})', params)
    counts['purged'] += max(cursor.rowcount or 0, 0)
    if recompute:
        recompute_canonicals(cursor, recompute)
    return counts


def purge_orphaned_tracks(
    conn: Any, dry_run: bool = False, batch_size: int = PURGE_BATCH, totals: dict[str, Any] | None = None
) -> dict[str, Any]:
    """Delete every unreferenced fileless track in batches; list the referenced ones that stay.

    Run it after `relink_orphaned_tracks`: an orphan that key could still relink is purged here
    only when it carries nothing worth relinking. Idempotent -- a second run finds only the kept
    orphans. With `dry_run` it surveys and counts, writing nothing. `totals['kept_list']` names
    up to KEPT_LIST_LIMIT kept orphans (id, title and each count); `totals`, when given, is filled
    in place so a caller can show progress.
    """
    if totals is None:
        totals = {}
    totals.update(empty_purge_totals(dry_run))
    with conn.cursor() as cursor:
        purge, kept = survey_orphans(cursor)
    totals['orphans'] = len(purge) + len(kept)
    totals['kept'] = len(kept)
    for name in ('listens', 'ratings', 'pinned', 'reviewed_labels'):
        totals[f'kept_{name}'] = sum(1 for row in kept if row[name])
    totals['kept_list'] = kept[:KEPT_LIST_LIMIT]
    if dry_run:
        totals['purged'] = len(purge)
        return totals
    for start in range(0, len(purge), batch_size):
        batch = purge[start : start + batch_size]
        with conn.cursor() as cursor:
            conn.begin()
            try:
                counts = purge_batch(cursor, batch)
                conn.commit()
            except Exception as exc:
                conn.rollback()
                totals['failed_batches'] += 1
                logger.warning('Purging orphaned tracks %s..%s failed: %s', batch[0], batch[-1], exc)
                continue
        totals['skipped_changed'] += len(batch) - counts['purged']
        for name, value in counts.items():
            totals[name] += value
    return totals
