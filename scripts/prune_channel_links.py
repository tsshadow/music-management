#!/usr/bin/env python3
"""
scripts/prune_channel_links.py

Removes track-to-channel links that no file path supports.

`library_track_channels` is derived data: a link exists because some file sits under
`<root>/<platform>/<channel>/`. Anything else in the table is a leftover -- from a file that moved,
from a channel that was merged into another, or from a run against an older set of rules.

It exists because of one such merge. `channels.normalized_name` was created with
`utf8mb4_general_ci`, which gives every character outside the Basic Multilingual Plane the same
collation weight, so two SoundCloud accounts styled with mathematical alphanumeric symbols compared
equal whenever they were the same length. Seven channels lost that comparison, and their tracks were
linked to the row that won it. Fixing the collation and re-running the backfill adds the correct
links; this removes the incorrect ones.

Deletes by exact (track_id, channel_id) pair, never wholesale: the table holds ~148.000 correct rows
and a rebuild would be a far bigger operation than the repair.

Usage:
    python3 scripts/prune_channel_links.py --dry-run
    python3 scripts/prune_channel_links.py
"""
import argparse
import sys

from services.common.channels import channel_from_path, normalize_channel_name
from services.common.config_store import ConfigStore as Settings
from services.music_manager.database import get_db_connection


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would be removed and delete nothing.')
    parser.add_argument('--batch', type=int, default=20000,
                        help='Rows to read per page (default 20000).')
    return parser.parse_args()


def supported_pairs(conn, music_root, batch):
    """Every (track_id, channel_id) that some file path actually puts there."""
    with conn.cursor() as cursor:
        cursor.execute('SELECT id, platform, normalized_name FROM channels')
        channel_ids = {(r['platform'], r['normalized_name']): r['id'] for r in cursor.fetchall()}

    pairs = set()
    last_id = 0
    while True:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id, file_path, track_id FROM library_media_files '
                'WHERE id > %s AND track_id IS NOT NULL ORDER BY id LIMIT %s',
                (last_id, batch))
            rows = cursor.fetchall()
        if not rows:
            break
        for row in rows:
            last_id = row['id']
            found = channel_from_path(row['file_path'], music_root)
            if not found:
                continue
            platform, name = found
            channel_id = channel_ids.get((platform, normalize_channel_name(name)))
            if channel_id is not None:
                pairs.add((row['track_id'], channel_id))
    return pairs


def main() -> int:
    args = parse_args()
    music_root = Settings().music_folder_path

    conn = get_db_connection()
    if not conn:
        print('Database connection failed', file=sys.stderr)
        return 1

    try:
        supported = supported_pairs(conn, music_root, args.batch)
        print(f'links supported by a file path: {len(supported)}')

        with conn.cursor() as cursor:
            cursor.execute('SELECT track_id, channel_id FROM library_track_channels')
            stored = {(r['track_id'], r['channel_id']) for r in cursor.fetchall()}
        print(f'links stored:                   {len(stored)}')

        unsupported = sorted(stored - supported)
        print(f'links with nothing behind them: {len(unsupported)}')

        if not unsupported:
            print('nothing to prune')
            return 0

        if args.dry_run:
            with conn.cursor() as cursor:
                for track_id, channel_id in unsupported[:10]:
                    cursor.execute('SELECT name FROM channels WHERE id = %s', (channel_id,))
                    row = cursor.fetchone()
                    name = row['name'] if row else '<gone>'
                    print(f'  track {track_id} -> channel {channel_id} ({name})')
            print('\nDry run only. Re-run without --dry-run to remove them.')
            return 0

        with conn.cursor() as cursor:
            for track_id, channel_id in unsupported:
                cursor.execute(
                    'DELETE FROM library_track_channels WHERE track_id = %s AND channel_id = %s',
                    (track_id, channel_id))
        conn.commit()
        print(f'{len(unsupported)} links removed')
    finally:
        conn.close()

    return 0


if __name__ == '__main__':
    raise SystemExit(main())
