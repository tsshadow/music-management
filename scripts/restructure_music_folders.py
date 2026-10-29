#!/usr/bin/env python3
"""
scripts/restructure_music_folders.py

Moves the library to the layout it should have had:

    /mnt/music/EPs/<label>/<release>   ->  /mnt/music/labels/<label>/<release>
    /mnt/music/EPs/__Free&None/...     ->  /mnt/music/songs/...
    /mnt/music/EPs/__TODO/...          ->  /mnt/music/import/...
    /mnt/music/Soundcloud/<channel>    ->  /mnt/music/channels/soundcloud/<channel>
    /mnt/music/Youtube/<channel>       ->  /mnt/music/channels/youtube/<channel>

`EPs` held three unrelated things: releases that are on a label, releases that are on none, and the
intake pile. Only the first is a label tree, which is why `__TODO` and `__Free&none` kept turning up
in the label chart. Splitting them apart is what makes "the folder above a release is its label"
true instead of nearly true.

**This is five directory renames, not 325.101 file moves.** Every move stays inside one mount, so
each is a metadata operation: fast, and undone just as cheaply with --revert.

What it touches besides the filesystem:

  - `library_media_files.file_path` and `file_path_hash`. The hash *is* the sha256 of the path, so
    both have to be rewritten together or the scanner sees every file as new.
  - `tagger_processed_files.filepath`, so nothing is needlessly re-tagged.
  - The `eps_folder_path` and `import_folder_path` settings, which are what the tagger anchors on.

What it deliberately does not touch:

  - Ratings. `rating_tracks.entity_id` is `library_tracks.track_uid`, which is derived from title,
    duration and primary artist -- not from the path. A move cannot lose a rating.
  - Listens. `scrobble_listens.track_id` points at `library_tracks.id`, also path-independent.
  - File contents and tags. Nothing is rewritten inside a file.

Afterwards LMS has to rescan: it keys its own library on paths, and every path just changed.

Usage:
    python3 scripts/restructure_music_folders.py --dry-run     # plan only, writes nothing
    python3 scripts/restructure_music_folders.py --apply
    python3 scripts/restructure_music_folders.py --revert      # put everything back
"""
import argparse
import hashlib
import os
import sys

from services.common.config_store import ConfigStore as Settings
from services.music_manager.database import get_db_connection

# (source, destination) relative to the music root, in the order they must happen: the two piles
# have to leave EPs before EPs itself is renamed, or they travel with it.
MOVES = [
    ('EPs/__Free&None', 'songs'),
    ('EPs/__TODO', 'import'),
    ('EPs', 'labels'),
    ('Soundcloud', 'channels/soundcloud'),
    ('Youtube', 'channels/youtube'),
]

# Settings that name a moved folder, and what they become.
SETTING_MOVES = {
    'eps_folder_path': ('EPs', 'labels'),
    'import_folder_path': ('EPs/__TODO', 'import'),
}


def parse_args():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument('--dry-run', action='store_true', help='Report the plan and write nothing.')
    mode.add_argument('--apply', action='store_true', help='Perform the restructure.')
    mode.add_argument('--revert', action='store_true', help='Undo a previous --apply.')
    parser.add_argument('--batch', type=int, default=5000, help='Rows per page (default 5000).')
    parser.add_argument('--api-base', default=None,
                        help='Base URL of the running music-manager API, e.g. '
                             'http://localhost:8000/api. Without it the two settings are only '
                             'reported, not changed.')
    parser.add_argument('--api-key', default=os.environ.get('MUMA_API_KEY') or os.environ.get('API_KEY'),
                        help='API key for --api-base. Defaults to MUMA_API_KEY from the environment, '
                             'which keeps it out of `ps` and shell history.')
    return parser.parse_args()


def planned_moves(root, revert):
    """The (source, destination) absolute pairs, in the order they must be performed."""
    pairs = [(os.path.join(root, src), os.path.join(root, dst)) for src, dst in MOVES]
    if revert:
        # Reversed both in direction and in order: EPs has to exist again before its two piles can
        # move back into it.
        return [(dst, src) for src, dst in reversed(pairs)]
    return pairs


def check_moves(pairs):
    """Refuse the whole plan unless every step can be taken. Half a restructure is the bad case."""
    problems = []
    for src, dst in pairs:
        if not os.path.isdir(src):
            problems.append(f'missing source: {src}')
        if os.path.exists(dst):
            problems.append(f'destination already exists: {dst}')
    return problems


def move_directories(pairs, dry_run):
    """Rename each directory, creating the parent of the destination when it does not exist."""
    for src, dst in pairs:
        print(f'  {src}  ->  {dst}')
        if dry_run:
            continue
        parent = os.path.dirname(dst)
        if parent:
            os.makedirs(parent, exist_ok=True)
        os.rename(src, dst)


def rewrite_paths(conn, pairs, dry_run, batch):
    """Rewrite every stored path, and the hash derived from it, to match the new location."""
    # `pairs` is already absolute and already in the right direction for a revert.
    prefixes = list(pairs)

    updated_media = 0
    updated_tagged = 0
    last_id = 0

    while True:
        with conn.cursor() as cursor:
            cursor.execute(
                'SELECT id, file_path FROM library_media_files WHERE id > %s ORDER BY id LIMIT %s',
                (last_id, batch))
            rows = cursor.fetchall()
        if not rows:
            break

        for row in rows:
            last_id = row['id']
            path = row['file_path'] or ''
            new_path = path
            for old_prefix, new_prefix in prefixes:
                if path.startswith(old_prefix + os.sep) or path == old_prefix:
                    new_path = new_prefix + path[len(old_prefix):]
                    break
            if new_path == path:
                continue
            updated_media += 1
            if dry_run:
                continue
            new_hash = hashlib.sha256(new_path.encode('utf-8')).hexdigest()
            with conn.cursor() as cursor:
                cursor.execute(
                    'UPDATE library_media_files SET file_path = %s, file_path_hash = %s '
                    'WHERE id = %s', (new_path, new_hash, row['id']))
        if not dry_run:
            conn.commit()

    # The tagger's own bookkeeping. Getting this wrong costs a re-tag, not data, so a simple
    # prefix replace per row is enough.
    with conn.cursor() as cursor:
        cursor.execute("SHOW TABLES LIKE 'tagger_processed_files'")
        if cursor.fetchone():
            cursor.execute('SELECT filepath FROM tagger_processed_files')
            for row in cursor.fetchall():
                path = row['filepath'] or ''
                for old_prefix, new_prefix in prefixes:
                    if path.startswith(old_prefix + os.sep):
                        updated_tagged += 1
                        if not dry_run:
                            with conn.cursor() as write:
                                write.execute(
                                    'UPDATE tagger_processed_files SET filepath = %s '
                                    'WHERE filepath = %s',
                                    (new_prefix + path[len(old_prefix):], path))
                        break
    if not dry_run:
        conn.commit()

    return updated_media, updated_tagged


def rewrite_settings(root, revert, dry_run, api_base, api_key):
    """Point the tagger's two anchors at the new folders.

    Sent to the running service rather than written locally: `ConfigStore` persists to a
    `data/config.json` beside whoever imports it, which is not the file production reads. With no
    `--api-base` the two values are only reported, so they can be changed by hand.
    """
    updates = {}
    for key, (old_rel, new_rel) in SETTING_MOVES.items():
        target_rel = old_rel if revert else new_rel
        updates[key] = os.path.join(root, target_rel)

    settings = Settings()
    for key, value in updates.items():
        print(f'  {key}: {settings.get(key)}  ->  {value}')

    if dry_run:
        return
    if not api_base:
        print('  no --api-base given; change these two settings yourself before the next scan')
        return

    import requests  # noqa: PLC0415 - only needed on the writing path

    response = requests.post(f'{api_base.rstrip("/")}/config/', json=updates,
                             headers={'X-API-Key': api_key or ''}, timeout=30)
    response.raise_for_status()
    print('  settings updated')


def main() -> int:
    args = parse_args()
    dry_run = args.dry_run
    root = str(Settings().music_folder_path or '').rstrip(os.sep)
    if not root or not os.path.isdir(root):
        print(f'Music root is not a directory: {root!r}', file=sys.stderr)
        return 1

    pairs = planned_moves(root, args.revert)

    print(f'Music root: {root}')

    problems = check_moves(pairs)
    if problems:
        print('Refusing -- the plan cannot be carried out in full:', file=sys.stderr)
        for problem in problems:
            print(f'  {problem}', file=sys.stderr)
        return 1

    # Connected before anything moves. A restructure that renames the folders and then cannot
    # reach the database leaves every stored path pointing at nothing.
    conn = get_db_connection()
    if not conn:
        print('Database connection failed -- nothing was moved', file=sys.stderr)
        return 1

    try:
        print('Step 1: directories')
        move_directories(pairs, dry_run)
        print('Step 2: stored paths')
        media, tagged = rewrite_paths(conn, pairs, dry_run, args.batch)
        print(f'  {media} media files, {tagged} tagger rows')
        print('Step 3: settings')
        rewrite_settings(root, args.revert, dry_run, args.api_base, args.api_key)
    finally:
        conn.close()

    if dry_run:
        print('\nDry run only. Re-run with --apply to perform it.')
    else:
        print('\nDone. LMS keys its library on paths, so trigger a full rescan there next.')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
