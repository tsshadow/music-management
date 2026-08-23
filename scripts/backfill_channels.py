#!/usr/bin/env python3
"""
scripts/backfill_channels.py

Turns the acquisition sources that are currently stored as record labels into channels.

`/api/analytics/top-labels` leads with `Soundcloud` (132.037 tracks), `Youtube` (30.779) and
`Telegram` (1.556) before the first real label, because the tagger writes the platform into the
publisher tag and the scanner stores a publisher as a label. `__TODO` and `__Free&none` are in the
same list without being labels either: one is the import folder's own name, the other is the pile of
music that genuinely has no label.

This script does three things, in order:

  1. Reads every file path in `library_media_files`, derives `(platform, channel)` from it, and
     creates the channel and its track link.
  2. Deletes the `library_track_labels` rows that point at a non-label.
  3. Deletes the now-unreferenced `library_labels` rows themselves.

Nothing on disk is touched and nothing is renamed: this is a classification change. A file keeps its
publisher tag -- it records where the file came from, which is true -- the database simply stops
calling that a label.

Idempotent: channels are inserted with INSERT IGNORE against a unique key, links with INSERT IGNORE,
and the deletes are filtered by name. Re-running finds nothing left to do.

Usage:
    python3 scripts/backfill_channels.py [--dry-run] [--batch 5000]

    --dry-run   Report what would change and write nothing. Run this first.
"""
import argparse
import sys

from services.common.channels import (
    NON_LABEL_PUBLISHERS,
    PLATFORM_FOLDERS,
    channel_from_path,
    normalize_channel_name,
)
from services.common.config_store import ConfigStore as Settings
from services.music_manager.database import get_db_connection


def non_label_names() -> list[str]:
    """Every label name that is not a label, as it might be spelled in the table."""
    names = set()
    for value in list(PLATFORM_FOLDERS) + list(NON_LABEL_PUBLISHERS):
        if value:
            names.add(value)
    return sorted(names)


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true',
                        help='Report what would change and write nothing.')
    parser.add_argument('--batch', type=int, default=5000,
                        help='Rows to read per page (default 5000).')
    return parser.parse_args()


def link_channels(conn, music_root, batch, dry_run):
    """Create a channel per platform account seen in a path, and link its tracks."""
    created_channels = set()
    linked = 0
    scanned = 0
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
            scanned += 1
            found = channel_from_path(row['file_path'], music_root)
            if not found:
                continue
            platform, name = found
            normalized = normalize_channel_name(name)
            if not normalized:
                continue
            created_channels.add((platform, normalized))
            if dry_run:
                linked += 1
                continue
            with conn.cursor() as cursor:
                cursor.execute(
                    'INSERT IGNORE INTO channels (platform, name, normalized_name) '
                    'VALUES (%s, %s, %s)', (platform, name, normalized))
                cursor.execute(
                    'SELECT id FROM channels WHERE platform = %s AND normalized_name = %s',
                    (platform, normalized))
                channel = cursor.fetchone()
                if not channel:
                    continue
                cursor.execute(
                    'INSERT IGNORE INTO library_track_channels (track_id, channel_id) '
                    'VALUES (%s, %s)', (row['track_id'], channel['id']))
                linked += cursor.rowcount
        if not dry_run:
            conn.commit()
        print(f'  ... {scanned} files read, {len(created_channels)} channels, {linked} links')

    return scanned, len(created_channels), linked


def drop_fake_labels(conn, dry_run):
    """Remove the label rows -- and their track links -- for things that are not labels."""
    names = non_label_names()
    placeholders = ', '.join(['%s'] * len(names))

    with conn.cursor() as cursor:
        cursor.execute(
            f'SELECT id, name FROM library_labels WHERE LOWER(name) IN ({placeholders})',
            names)
        labels = cursor.fetchall()

    if not labels:
        print('  no non-label labels left')
        return 0, 0

    ids = [row['id'] for row in labels]
    id_placeholders = ', '.join(['%s'] * len(ids))

    with conn.cursor() as cursor:
        cursor.execute(
            f'SELECT COUNT(*) AS c FROM library_track_labels WHERE label_id IN ({id_placeholders})',
            ids)
        link_count = cursor.fetchone()['c']

    for row in labels:
        print(f"  {row['name']}")
    print(f'  {len(labels)} labels, {link_count} track links')

    if dry_run:
        return len(labels), link_count

    with conn.cursor() as cursor:
        cursor.execute(
            f'DELETE FROM library_track_labels WHERE label_id IN ({id_placeholders})', ids)
        cursor.execute(f'DELETE FROM library_labels WHERE id IN ({id_placeholders})', ids)
    conn.commit()
    return len(labels), link_count


def main() -> int:
    args = parse_args()
    music_root = Settings().music_folder_path

    conn = get_db_connection()
    if not conn:
        print('Database connection failed', file=sys.stderr)
        return 1

    mode = 'DRY RUN -- nothing is written' if args.dry_run else 'writing'
    print(f'Backfilling channels ({mode}), music root: {music_root}')

    try:
        print('Step 1: channels from file paths')
        scanned, channels, linked = link_channels(conn, music_root, args.batch, args.dry_run)
        print(f'  {scanned} files, {channels} channels, {linked} track links')

        print('Step 2 and 3: labels that are not labels')
        labels, links = drop_fake_labels(conn, args.dry_run)
        print(f'  {labels} labels and {links} track links removed')
    finally:
        conn.close()

    if args.dry_run:
        print('\nDry run only. Re-run without --dry-run to apply.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
