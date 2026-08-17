"""Backfill for the festival tags: hand files back to the tagger, and clear the old atom.

Two things stand between a new row in `rules_festivals` and a card in the app:

1. The tagger skips every file whose mtime it has already seen, so a file that was
   processed before the festival was known is never looked at again. Setting
   `needs_rescan` on its row in `tagger_processed_files` is what puts it back in the
   queue -- the tagger clears the flag itself once it has processed the file.
2. Some m4a files carry a second, differently-cased MP4 atom
   `----:com.apple.iTunes:Festival` from a tagging round that predates this repo. LMS
   reads it alongside the current `...:FESTIVAL` atom, which is where the "Defqon 2024"
   card comes from. Removing it makes the stale cluster disappear at the next scan.

Both steps are opt-in. Without --apply the script only reports what it would do.

    python -m tools.retag_festivals                          # report
    python -m tools.retag_festivals --apply                  # queue the re-tag
    python -m tools.retag_festivals --apply --strip-legacy-atom
    python -m tools.retag_festivals --apply --prefix /mnt/music/Livesets
"""
import argparse
import logging
import os
import sys

from dotenv import load_dotenv
from mutagen.mp4 import MP4

from services.common.Helpers.DatabaseConnector import DatabaseConnector

load_dotenv()

# The folders that hold sets. Youtube is included because that is where the bulk of
# the recordings live; EPs and Soundcloud hold tracks and are deliberately left alone.
DEFAULT_PREFIXES = (
    '/mnt/music/Livesets',
    '/mnt/music/Warm Up Mixes',
    '/mnt/music/Podcasts',
    '/mnt/music/Top 100',
    '/mnt/music/Youtube',
)

LEGACY_ATOM = '----:com.apple.iTunes:Festival'
CURRENT_ATOM = '----:com.apple.iTunes:FESTIVAL'


def count_candidates(connection, prefixes) -> dict[str, int]:
    """How many already-processed rows sit under each prefix."""
    counts = {}
    with connection.cursor() as cursor:
        for prefix in prefixes:
            cursor.execute(
                'SELECT COUNT(*) FROM tagger_processed_files WHERE filepath LIKE %s AND needs_rescan = 0',
                (prefix + '%',),
            )
            counts[prefix] = cursor.fetchone()[0]
    return counts


def mark_for_rescan(connection, prefixes) -> int:
    """Flag those rows so the next tagger run reads the files again."""
    marked = 0
    with connection.cursor() as cursor:
        for prefix in prefixes:
            cursor.execute(
                'UPDATE tagger_processed_files SET needs_rescan = 1 WHERE filepath LIKE %s AND needs_rescan = 0',
                (prefix + '%',),
            )
            marked += cursor.rowcount
    connection.commit()
    return marked


def find_legacy_atoms(prefixes) -> list[str]:
    """Every m4a under the prefixes that still carries the old mixed-case atom."""
    found = []
    for prefix in prefixes:
        if not os.path.isdir(prefix):
            continue
        for dirpath, _dirnames, filenames in os.walk(prefix):
            for filename in filenames:
                if not filename.lower().endswith('.m4a'):
                    continue
                path = os.path.join(dirpath, filename)
                try:
                    tags = MP4(path).tags or {}
                except Exception:
                    continue
                if LEGACY_ATOM in tags:
                    found.append(path)
    return found


def strip_legacy_atom(path: str) -> bool:
    """Remove only the mixed-case atom. The upper-case one holds the current label."""
    audio = MP4(path)
    tags = audio.tags or {}
    if LEGACY_ATOM not in tags:
        return False
    del tags[LEGACY_ATOM]
    audio.save()
    return True


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description='Queue files for re-tagging and clear the legacy festival atom.')
    parser.add_argument('--apply', action='store_true', help='actually write; without it nothing changes')
    parser.add_argument('--prefix', action='append', dest='prefixes', metavar='PATH',
                        help='limit to this path prefix (repeatable, defaults to the set folders)')
    parser.add_argument('--strip-legacy-atom', action='store_true',
                        help='also remove ----:com.apple.iTunes:Festival from m4a files')
    args = parser.parse_args(argv)

    logging.basicConfig(level=logging.INFO, format='%(message)s')
    prefixes = tuple(args.prefixes) if args.prefixes else DEFAULT_PREFIXES

    connector = DatabaseConnector()
    with connector.connection() as connection:
        counts = count_candidates(connection, prefixes)
        for prefix, count in counts.items():
            logging.info('%8d already-processed files under %s', count, prefix)
        total = sum(counts.values())
        if args.apply:
            marked = mark_for_rescan(connection, prefixes)
            logging.info('Marked %d files for re-tagging.', marked)
        else:
            logging.info('Would mark %d files for re-tagging (use --apply).', total)

    if args.strip_legacy_atom:
        stale = find_legacy_atoms(prefixes)
        logging.info('%d m4a files still carry %s', len(stale), LEGACY_ATOM)
        if args.apply:
            cleared = sum(1 for path in stale if strip_legacy_atom(path))
            logging.info('Cleared the legacy atom on %d files.', cleared)

    if args.apply:
        logging.info('Now run the tagger, which triggers an LMS scan when it finishes.')
    return 0


if __name__ == '__main__':
    sys.exit(main())
