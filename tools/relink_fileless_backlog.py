"""Relink or purge the fileless tracks the import-pack rescans left behind (GitLab issue #71).

Until the scanner's file-name key (MR !1420), every weekly pack left about 100 tracks that no
media file pointed at: the full scan indexed a release inside `import/<pack>/`, the importer then
moved and retagged it, and the next scan made a new track. On production on 2026-11-12 there were
1,019 such tracks; 185 of them have listens and 1 has a rating.

This script handles that backlog in three steps:

1. Relink. An orphan whose title is the same as the title of exactly one track with a file, and
   whose duration is within 5 ms of that track's, gets its ratings, listens, analysis and works
   moved to that track (`track_relink.relink_track`), and is deleted. A track with a file whose
   title and length match to the millisecond is the same recording.
2. Purge. An orphan left after step 1 that no listen, rating, work pin or reviewed ml label points
   at is deleted (`orphan_purge.purge_batch`, which checks each guard again with the rows locked).
3. List. The orphans left after both steps have a listen or a rating. They stay, and the run
   prints each one for a person to decide.

The run is a dry run unless `--apply` is given. The dry run prints every match on an orphan made
before `--recent-since` (default 2026-10-01): those predate the import-pack cause, so a person
reads them before the apply. `--skip-older` leaves them out of step 1; without history they then
fall to step 2 like any other leftover.

`--apply` first writes a JSON backup (0600) of every row the two steps may change or delete to
BACKUP_DIR, then relinks each orphan in its own transaction and purges in batches of 1000.
`--rollback BACKUP.json` puts every backed-up row back in one transaction, and deletes the BPM
rows the relink moved onto a track that had none. A second apply finds nothing to do.

Runs inside the music-manager container, with the script on stdin:

    python - [--apply] [--skip-older] [--recent-since YYYY-MM-DD] [--sample N] < relink_fileless_backlog.py
    python - --rollback /app/data/fileless-backlog/<file>.json < relink_fileless_backlog.py
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import time
from collections import Counter
from typing import Any

# The container sets PYTHONPATH=/app, so `python -` there finds the services package.
from services.music_manager import orphan_purge, track_relink

BACKUP_DIR = os.environ.get('FILELESS_BACKLOG_BACKUP_DIR', '/app/data/fileless-backlog')

#: Two durations closer than this are the same file: 5 ms, well inside one MP3 frame (26 ms).
DURATION_TOLERANCE_SECS = 0.005

RECENT_SINCE = '2026-10-01'

RELINK, PURGE, KEEP = 'relink', 'purge', 'keep'

_ORPHANS = """
    SELECT t.id, t.track_uid, t.title, t.duration_secs, t.created_at
    FROM library_tracks t
    WHERE NOT EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = t.id)
    ORDER BY t.id
"""

# Every track with a file that has an orphan's title and length. Title equality is the column's
# collation (utf8mb4_general_ci on production), the same comparison the 2026-11-12 count used.
_MATCHES = """
    SELECT o.id AS orphan_id, s.id AS target_id
    FROM library_tracks o
    JOIN library_tracks s ON s.title = o.title AND s.id <> o.id AND ABS(s.duration_secs - o.duration_secs) < %s
    WHERE NOT EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = o.id)
      AND EXISTS (SELECT 1 FROM library_media_files mf WHERE mf.track_id = s.id)
"""

#: Tables restored from a backup, with their primary key. Junction tables have no single key and
#: are only ever re-inserted.
KEYED_TABLES = {
    'library_tracks': 'id',
    'library_track_effective_bpm': 'track_id',
    'library_track_audio_features': 'id',
    'library_track_ml_labels': 'id',
    'library_track_bpm': 'track_uid',
    'library_track_bpm_manual': 'track_uid',
    'rating_tracks': 'id',
    'scrobble_listens': 'id',
    'library_works': 'id',
}
LINK_TABLES = orphan_purge.LINK_TABLES
BPM_TABLES = ('library_track_bpm', 'library_track_bpm_manual')
RESTORE_ORDER = (
    'library_tracks',
    *LINK_TABLES,
    'library_track_effective_bpm',
    'library_track_audio_features',
    'library_track_ml_labels',
    *BPM_TABLES,
    'rating_tracks',
    'scrobble_listens',
    'library_works',
)
_IDENTIFIER = re.compile(r'^[a-z_][a-z0-9_]*$')


def _all(cursor: Any, sql: str, params: tuple = ()) -> list[dict]:
    """Every row of one query, as dicts."""
    cursor.execute(sql, params)
    return list(cursor.fetchall())


def _marks(values: list) -> str:
    """The `%s, %s, ...` list for an IN clause."""
    return ', '.join(['%s'] * len(values))


# --- the survey -----------------------------------------------------------------------------------


def _plan(orphan: dict, found: list[int], ref: dict, recent_since: str) -> dict:
    """One orphan's facts: its match, when it was made, and what a user made points at it."""
    created = str(orphan['created_at'] or '')
    return {
        'orphan_id': int(orphan['id']),
        'track_uid': orphan['track_uid'],
        'title': orphan['title'],
        'duration': orphan['duration_secs'],
        'created_at': created,
        'recent': created >= recent_since,
        'matches': len(found),
        'target_id': found[0] if len(found) == 1 else None,
        'listens': int(ref.get('listens', 0)),
        'ratings': int(ref.get('ratings', 0)),
        'pinned': int(ref.get('pinned', 0)),
        'reviewed_labels': int(ref.get('reviewed_labels', 0)),
    }


def survey(cursor: Any, recent_since: str = RECENT_SINCE, skip_older: bool = False) -> list[dict]:
    """One plan per fileless track: relink to its one match, purge it, or keep it for a person."""
    targets: dict[int, set[int]] = {}
    for row in _all(cursor, _MATCHES, (DURATION_TOLERANCE_SECS,)):
        targets.setdefault(int(row['orphan_id']), set()).add(int(row['target_id']))
    purgeable, kept = orphan_purge.survey_orphans(cursor)
    purgeable_ids = set(purgeable)
    refs = {row['id']: row for row in kept}
    plans = []
    for orphan in _all(cursor, _ORPHANS):
        track_id = int(orphan['id'])
        plan = _plan(orphan, sorted(targets.get(track_id, ())), refs.get(track_id, {}), recent_since)
        if plan['target_id'] is not None and (plan['recent'] or not skip_older):
            plan['bucket'] = RELINK
        elif track_id in purgeable_ids:
            plan['bucket'] = PURGE
        else:
            plan['bucket'] = KEEP
        plans.append(plan)
    _describe_targets(cursor, plans)
    return plans


def _describe_targets(cursor: Any, plans: list[dict]) -> None:
    """Add the match's title and one of its file paths, so a person can read each relink."""
    ids = sorted({plan['target_id'] for plan in plans if plan['target_id'] is not None})
    for start in range(0, len(ids), 1000):
        chunk = ids[start : start + 1000]
        tracks = {
            int(row['id']): row
            for row in _all(
                cursor, f'SELECT id, track_uid, title FROM library_tracks WHERE id IN ({_marks(chunk)})', tuple(chunk)
            )
        }
        paths = {
            int(row['track_id']): row['path']
            for row in _all(
                cursor,
                'SELECT track_id, MIN(file_path) AS path FROM library_media_files '
                f'WHERE track_id IN ({_marks(chunk)}) GROUP BY track_id',
                tuple(chunk),
            )
        }
        for plan in plans:
            target = tracks.get(plan['target_id'] or -1)
            if target is not None:
                plan['target_uid'] = target['track_uid']
                plan['target_title'] = target['title']
                plan['target_path'] = paths.get(plan['target_id'])


# --- the report -----------------------------------------------------------------------------------


def _relink_line(plan: dict) -> str:
    """One relink, readable: the orphan, its history, and the file it joins."""
    return (
        f'   orphan {plan["orphan_id"]} created {plan["created_at"]}, {plan["listens"]} listens, '
        f'{plan["ratings"]} ratings: "{plan["title"]}" ({plan["duration"]:.3f} s)\n'
        f'      -> track {plan["target_id"]}: {plan.get("target_path")}'
    )


def report(plans: list[dict], sample: int, recent_since: str = RECENT_SINCE) -> None:
    """Print the counts, every older match, a sample of the recent ones, and every kept track."""
    counts = Counter((plan['bucket'], plan['recent']) for plan in plans)
    print(f'{len(plans)} fileless tracks. Made before {recent_since} / since:')
    for bucket in (RELINK, PURGE, KEEP):
        print(f'   {bucket:<7} {counts[(bucket, False)]:>6} / {counts[(bucket, True)]:<6}')
    older = [plan for plan in plans if plan['target_id'] is not None and not plan['recent']]
    print(f'\nOlder matches (made before {recent_since}), every one ({len(older)}):')
    for plan in older:
        skipped = '' if plan['bucket'] == RELINK else f'   [not relinked: {plan["bucket"]}]'
        print(_relink_line(plan) + skipped)
    recent = [plan for plan in plans if plan['bucket'] == RELINK and plan['recent']]
    print(f'\nRecent relinks ({len(recent)}), the first {min(sample, len(recent))}:')
    for plan in recent[:sample]:
        print(_relink_line(plan))
    keep = [plan for plan in plans if plan['bucket'] == KEEP]
    print(f'\nKept for a person ({len(keep)}): a listen, rating, pin or reviewed label, and no single match.')
    for plan in keep:
        why = 'no match' if plan['matches'] == 0 else f'{plan["matches"]} matches' if plan['matches'] > 1 else '1 match'
        print(
            f'   track {plan["orphan_id"]} created {plan["created_at"]}: "{plan["title"]}" '
            f'({plan["duration"] or 0:.1f} s) -- {plan["listens"]} listens, {plan["ratings"]} ratings, '
            f'{plan["pinned"]} pins, {plan["reviewed_labels"]} reviewed labels; {why}'
        )


# --- the backup -----------------------------------------------------------------------------------


def backup_rows(cursor: Any, plans: list[dict]) -> tuple[dict[str, list[dict]], list[dict]]:
    """Every row the apply may change or delete, and the BPM keys a relink may create."""
    rows: dict[str, dict[Any, dict]] = {table: {} for table in RESTORE_ORDER}
    absent: list[dict] = []

    def keep(table: str, found: list[dict]) -> None:
        for row in found:
            key = row[KEYED_TABLES[table]] if table in KEYED_TABLES else tuple(sorted(row.items()))
            rows[table][key] = row

    for plan in plans:
        if plan['bucket'] == KEEP:
            continue
        track_id, uid = plan['orphan_id'], plan['track_uid']
        keep('library_tracks', _all(cursor, 'SELECT * FROM library_tracks WHERE id = %s', (track_id,)))
        for table in (*LINK_TABLES, 'library_track_effective_bpm'):
            keep(table, _all(cursor, f'SELECT * FROM {table} WHERE track_id = %s', (track_id,)))  # noqa: S608
        for table in ('library_track_audio_features', 'library_track_ml_labels'):
            keep(table, _all(cursor, f'SELECT * FROM {table} WHERE internal_track_id = %s', (track_id,)))  # noqa: S608
        keep(
            'library_works',
            _all(
                cursor,
                'SELECT * FROM library_works WHERE canonical_track_id = %s OR pinned_track_id = %s '
                'OR previous_canonical_track_id = %s',
                (track_id, track_id, track_id),
            ),
        )
        keep('scrobble_listens', _all(cursor, 'SELECT * FROM scrobble_listens WHERE track_id = %s', (track_id,)))
        if not uid:
            continue
        keep(
            'library_track_ml_labels', _all(cursor, 'SELECT * FROM library_track_ml_labels WHERE track_id = %s', (uid,))
        )
        mine = _all(cursor, "SELECT * FROM rating_tracks WHERE entity_type = 'track' AND entity_id = %s", (uid,))
        keep('rating_tracks', mine)
        target_uid = plan.get('target_uid') if plan['bucket'] == RELINK else None
        if not target_uid:
            continue
        for row in mine:
            keep(
                'rating_tracks',
                _all(
                    cursor,
                    "SELECT * FROM rating_tracks WHERE entity_type = 'track' AND entity_id = %s AND username = %s",
                    (target_uid, row['username']),
                ),
            )
        for table in BPM_TABLES:
            old = _all(cursor, f'SELECT * FROM {table} WHERE track_uid = %s', (uid,))  # noqa: S608
            keep(table, old)
            if old and not _all(cursor, f'SELECT track_uid FROM {table} WHERE track_uid = %s', (target_uid,)):  # noqa: S608
                absent.append({'table': table, 'track_uid': target_uid})
    return {table: list(found.values()) for table, found in rows.items()}, absent


def write_backup(plans: list[dict], rows: dict[str, list[dict]], absent: list[dict]) -> str:
    """The plans, the rows and the absent BPM keys, as JSON, 0600, written before anything else."""
    os.makedirs(BACKUP_DIR, mode=0o700, exist_ok=True)
    path = os.path.join(BACKUP_DIR, f'fileless-backlog-{time.strftime("%Y%m%d-%H%M%S")}.json')
    temporary = path + '.part'
    with open(os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600), 'w', encoding='utf-8') as handle:
        json.dump(
            {'format': 1, 'plans': plans, 'rows': rows, 'absent': absent},
            handle,
            ensure_ascii=False,
            indent=1,
            default=str,
        )
    os.replace(temporary, path)
    return path


# --- writing --------------------------------------------------------------------------------------


def run_apply(connection: Any, cursor: Any, plans: list[dict]) -> Counter:
    """Write the backup, relink each match in its own transaction, then purge in batches."""
    rows, absent = backup_rows(cursor, plans)
    connection.rollback()
    backup = write_backup(plans, rows, absent)
    print(f'\nBackup: {backup}', flush=True)
    outcome: Counter = Counter()
    for plan in plans:
        if plan['bucket'] != RELINK:
            continue
        try:
            connection.begin()
            counts = None
            if track_relink.track_has_media_file(cursor, plan['target_id']):
                counts = track_relink.relink_track(cursor, plan['orphan_id'], plan['target_id'])
            connection.commit()
        except Exception as error:  # noqa: BLE001 - one bad row must not stop the rest
            connection.rollback()
            outcome['relink failed'] += 1
            print(f'   relink {plan["orphan_id"]} -> {plan["target_id"]} failed: {error}')
            continue
        if counts is None:
            outcome['relink skipped, changed since the survey'] += 1
            continue
        outcome['relinked'] += 1
        outcome.update({name: value for name, value in counts.items() if name != 'tracks_deleted'})
    purge = [plan['orphan_id'] for plan in plans if plan['bucket'] == PURGE]
    for start in range(0, len(purge), orphan_purge.PURGE_BATCH):
        batch = purge[start : start + orphan_purge.PURGE_BATCH]
        try:
            connection.begin()
            counts = orphan_purge.purge_batch(cursor, batch)
            connection.commit()
        except Exception as error:  # noqa: BLE001 - the next batch is independent
            connection.rollback()
            outcome['purge batch failed'] += 1
            print(f'   purge {batch[0]}..{batch[-1]} failed: {error}')
            continue
        outcome.update(counts)
        outcome['purge skipped, changed since the survey'] += len(batch) - counts['purged']
    print('\nDone: ' + ', '.join(f'{name} {count}' for name, count in sorted(outcome.items()) if count))
    print(f'Undo: --rollback {backup}')
    return outcome


def restore_rows(connection: Any, cursor: Any, saved: dict) -> Counter:
    """Put every backed-up row back as it was, and drop the BPM rows a relink created."""
    done: Counter = Counter()
    for marker in saved.get('absent', []):
        if marker['table'] not in BPM_TABLES:
            raise ValueError(f'refusing an absent marker for {marker["table"]}')
        cursor.execute(f'DELETE FROM {marker["table"]} WHERE track_uid = %s', (marker['track_uid'],))  # noqa: S608
        done[f'{marker["table"]} created row deleted'] += max(cursor.rowcount or 0, 0)
    for table in RESTORE_ORDER:
        for row in saved['rows'].get(table, []):
            columns = list(row)
            if not all(_IDENTIFIER.match(column) for column in columns):
                raise ValueError(f'refusing a column name in {table}: {columns}')
            key = KEYED_TABLES.get(table)
            if key is None:
                where = ' AND '.join(f'{column} = %s' for column in columns)
                if _all(cursor, f'SELECT 1 AS present FROM {table} WHERE {where}', tuple(row.values())):  # noqa: S608
                    continue
            elif _all(cursor, f'SELECT 1 AS present FROM {table} WHERE {key} = %s', (row[key],)):  # noqa: S608
                assignments = ', '.join(f'{column} = %s' for column in columns if column != key)
                values = tuple(row[column] for column in columns if column != key)
                if assignments:
                    cursor.execute(f'UPDATE {table} SET {assignments} WHERE {key} = %s', (*values, row[key]))  # noqa: S608
                done[f'{table} reset'] += 1
                continue
            cursor.execute(
                f'INSERT INTO {table} ({", ".join(columns)}) VALUES ({_marks(columns)})',  # noqa: S608
                tuple(row.values()),
            )
            done[f'{table} inserted'] += 1
    connection.commit()
    return done


def run_rollback(connection: Any, cursor: Any, backup: str) -> Counter:
    """Restore a backup in one transaction."""
    with open(backup, encoding='utf-8') as handle:
        saved = json.load(handle)
    try:
        connection.begin()
        done = restore_rows(connection, cursor, saved)
    except Exception:
        connection.rollback()
        raise
    print('Restored: ' + (', '.join(f'{name} {count}' for name, count in sorted(done.items())) or 'nothing'))
    return done


# --- the run --------------------------------------------------------------------------------------


def _db_connection() -> Any:
    """music-manager's own database connection, from the container's environment."""
    from services.common.Helpers.DatabaseConnector import DatabaseConnector  # pylint: disable=import-outside-toplevel

    return DatabaseConnector().connect()


def _dict_cursor(connection: Any) -> Any:
    """A cursor that returns rows as dicts, as track_relink and orphan_purge expect."""
    import pymysql.cursors  # pylint: disable=import-outside-toplevel

    return connection.cursor(pymysql.cursors.DictCursor)


def run(connection: Any, cursor: Any, args: argparse.Namespace) -> int:
    """A dry run, an apply or a rollback on an open connection."""
    if args.rollback:
        run_rollback(connection, cursor, args.rollback)
        return 0
    print('APPLY' if args.apply else 'DRY RUN', flush=True)
    plans = survey(cursor, args.recent_since, args.skip_older)
    report(plans, args.sample, args.recent_since)
    if args.apply:
        run_apply(connection, cursor, plans)
    else:
        connection.rollback()
        print('\nDry run: nothing written. Run again with --apply to write.')
    return 0


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    """The command line."""
    parser = argparse.ArgumentParser(description=(__doc__ or '').split('\n', 1)[0])
    parser.add_argument('--apply', action='store_true', help='write; without it nothing is written')
    parser.add_argument('--rollback', metavar='BACKUP', help='restore a backup written by --apply')
    parser.add_argument('--skip-older', action='store_true', help='do not relink orphans made before --recent-since')
    parser.add_argument('--recent-since', default=RECENT_SINCE, help='the date that splits older from recent')
    parser.add_argument('--sample', type=int, default=20, help='how many recent relinks to print')
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    """Parse the flags and run against music-manager's database."""
    args = parse_args(argv)
    connection = _db_connection()
    try:
        return run(connection, _dict_cursor(connection), args)
    finally:
        connection.close()


if __name__ == '__main__':
    sys.exit(main())
