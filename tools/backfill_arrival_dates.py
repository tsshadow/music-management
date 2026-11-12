"""Fill `library_tracks.arrived_at` for tracks from before arrival dates were kept.

The rule is in docs/designs/wrapped-page/technical.md ("Arrival dates"). A track whose
`arrived_at` is NULL gets the earliest of these dates over its files:

* the SoundCloud archive's `added_at`, matched on `filename` = the file's path;
* the YouTube archive's `added_at`, matched on `path` = the file's path;
* the ingestion record's `recorded_at`, matched on the path hash (kept since 2026-09-08).

A date is only accepted when it is no later than one hour after the track row was created:
a later date belongs to a redownload or a re-ingest, not to the arrival, and the track stays
unknown. `arrived_source` comes from the top folder of the file that gave the date.

All dates are UTC: the database runs in UTC and the scanner writes UTC_TIMESTAMP().

Usage (inside the music-manager container, which has pymysql and the DB_* environment):

    python3 tools/backfill_arrival_dates.py                 # dry run: counts only
    python3 tools/backfill_arrival_dates.py --apply --rollback /backup/arrival-ids.txt
    python3 tools/backfill_arrival_dates.py --undo /backup/arrival-ids.txt

`--apply` writes the id of every track it fills to the rollback file first; `--undo` sets
those tracks back to NULL. A second `--apply` finds nothing left to do for the same tracks.
"""

from __future__ import annotations

import argparse
import os
import sys
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.common.arrival import arrival_source  # noqa: E402  # pylint: disable=wrong-import-position

#: How far after its row's creation a date may lie and still be the arrival.
GRACE = timedelta(hours=1)
BATCH = 1000

TRACKS_SQL = 'SELECT id, created_at FROM library_tracks WHERE arrived_at IS NULL'

CANDIDATE_SQL = {
    'soundcloud_archive': """
        SELECT m.track_id, m.file_path, a.added_at AS at
        FROM library_media_files m
        JOIN library_tracks t ON t.id = m.track_id AND t.arrived_at IS NULL
        JOIN downloads_soundcloud_archive a ON a.filename = m.file_path
        WHERE a.added_at IS NOT NULL
    """,
    'youtube_archive': """
        SELECT m.track_id, m.file_path, a.added_at AS at
        FROM library_media_files m
        JOIN library_tracks t ON t.id = m.track_id AND t.arrived_at IS NULL
        JOIN downloads_youtube_archive a ON a.path = m.file_path
        WHERE a.added_at IS NOT NULL
    """,
    'ingestion': """
        SELECT m.track_id, m.file_path, i.recorded_at AS at
        FROM library_media_files m
        JOIN library_tracks t ON t.id = m.track_id AND t.arrived_at IS NULL
        JOIN library_ingestion_records i ON i.file_path_hash = m.file_path_hash
        WHERE i.recorded_at IS NOT NULL
    """,
}

UPDATE_SQL = 'UPDATE library_tracks SET arrived_at = %s, arrived_source = %s WHERE id = %s AND arrived_at IS NULL'
UNDO_SQL = 'UPDATE library_tracks SET arrived_at = NULL, arrived_source = NULL WHERE id = %s'


@dataclass(frozen=True)
class Arrival:
    """The date a track gets, and the file and table it came from."""

    track_id: int
    at: datetime
    source: str
    evidence: str


@dataclass
class Plan:
    """What a run would write, and why the other tracks stay unknown."""

    fills: list[Arrival]
    unknown: int
    too_late: int

    def describe(self) -> str:
        """A short report for the operator: counts only, no paths."""
        by_source = Counter(a.source for a in self.fills)
        by_evidence = Counter(a.evidence for a in self.fills)
        lines = [
            f'Tracks to fill: {len(self.fills)}',
            f'  by source:   {dict(sorted(by_source.items()))}',
            f'  by evidence: {dict(sorted(by_evidence.items()))}',
            f'Left unknown, no date found: {self.unknown}',
            f'Left unknown, every date later than the row (a redownload): {self.too_late}',
        ]
        return '\n'.join(lines)


def plan(cursor, music_root: str) -> Plan:
    """Work out every track's arrival under the acceptance rule."""
    cursor.execute(TRACKS_SQL)
    created = {int(r['id']): r['created_at'] for r in cursor.fetchall() or []}
    best: dict[int, tuple[datetime, str, str]] = {}
    seen: set[int] = set()
    for evidence, sql in CANDIDATE_SQL.items():
        cursor.execute(sql)
        for row in cursor.fetchall() or []:
            track_id = int(row['track_id'])
            if track_id not in created:
                continue
            seen.add(track_id)
            at = row['at']
            if created[track_id] is None or at > created[track_id] + GRACE:
                continue
            if track_id not in best or at < best[track_id][0]:
                best[track_id] = (at, row['file_path'], evidence)
    fills = [
        Arrival(track_id, at, arrival_source(path, music_root), evidence)
        for track_id, (at, path, evidence) in sorted(best.items())
    ]
    return Plan(fills=fills, unknown=len(created) - len(seen), too_late=len(seen) - len(best))


def apply(conn, fills: list[Arrival], rollback_path: str) -> int:
    """Write the rollback file, then the dates in batches. Returns the rows changed."""
    with open(rollback_path, 'w', encoding='utf-8') as handle:
        handle.writelines(f'{a.track_id}\n' for a in fills)
    changed = 0
    for start in range(0, len(fills), BATCH):
        batch = fills[start : start + BATCH]
        with conn.cursor() as cursor:
            for a in batch:
                cursor.execute(UPDATE_SQL, (a.at, a.source, a.track_id))
                changed += cursor.rowcount or 0
        conn.commit()
    return changed


def undo(conn, rollback_path: str) -> int:
    """Set the tracks in a rollback file back to an unknown arrival."""
    with open(rollback_path, encoding='utf-8') as handle:
        ids = [int(line) for line in handle if line.strip()]
    for start in range(0, len(ids), BATCH):
        with conn.cursor() as cursor:
            for track_id in ids[start : start + BATCH]:
                cursor.execute(UNDO_SQL, (track_id,))
        conn.commit()
    return len(ids)


def _connection():  # pragma: no cover - production only
    import pymysql  # pylint: disable=import-outside-toplevel

    return pymysql.connect(
        host=os.getenv('DB_HOST', 'db'),
        port=int(os.getenv('DB_PORT', '3306')),
        user=os.getenv('DB_USER', 'music-management'),
        password=os.getenv('DB_PASS', ''),
        database=os.getenv('DB_DB', 'music-management'),
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def main(argv: list[str] | None = None) -> int:  # pragma: no cover - thin CLI over tested functions
    """Dry run by default; --apply needs --rollback; --undo reads one."""
    parser = argparse.ArgumentParser(description=__doc__.split('\n\n', 1)[0])
    parser.add_argument('--apply', action='store_true')
    parser.add_argument('--rollback', help='file to write the filled track ids to (with --apply)')
    parser.add_argument('--undo', metavar='ROLLBACK_FILE')
    parser.add_argument('--music-root', default=os.getenv('music_folder_path', '/mnt/music'))
    args = parser.parse_args(argv)
    conn = _connection()
    try:
        if args.undo:
            print(f'Reset {undo(conn, args.undo)} tracks to an unknown arrival')
            return 0
        with conn.cursor() as cursor:
            result = plan(cursor, args.music_root)
        print(result.describe())
        if not args.apply:
            print('Dry run: nothing written. Add --apply --rollback FILE to write.')
            return 0
        if not args.rollback:
            parser.error('--apply needs --rollback FILE')
        print(f'Filled {apply(conn, result.fills, args.rollback)} tracks; ids in {args.rollback}')
        return 0
    finally:
        conn.close()


if __name__ == '__main__':  # pragma: no cover
    sys.exit(main())
