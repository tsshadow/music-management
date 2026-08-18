"""Backfills the original release date onto label releases already in the library.

The scene NFO is moved into the label folder alongside the audio at import time, so every release
that ever had one can still be dated without re-downloading anything. Dry run by default: it reports
what it would write before anything touches a file.
"""
import argparse
import logging
import os
import sys
from collections import Counter

from dotenv import load_dotenv

from services.tagger.constants import ORIGINAL_DATE
from services.tagger.Song import NfoDate

# The scene group overrides come from the database, and DatabaseConnector reads its parameters
# straight from the environment. The compose stack injects them, but run from a checkout they live
# only in the repository's .env. load_dotenv leaves variables already set on the command line
# alone, so an override like DB_HOST=192.0.2.27 still wins.
load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.aac', '.wav')
DEFAULT_ROOT = '/mnt/music/EPs'

# services.common.Helpers.Cache builds every lookup helper at import time, each one opening a
# database connection, so it is imported inside main() rather than here: planning is pure and its
# tests must not need a database.


def plan_release_dates(root, format_helper):
    """`[(directory, iso_date)]` for every release directory that resolves to a date."""
    planned = []
    for current, _dirs, files in os.walk(root):
        if not any(name.lower().endswith(AUDIO_EXTENSIONS) for name in files):
            continue
        dirname = os.path.basename(current)
        text = NfoDate.read_nfo(current)
        if not text:
            continue
        group = NfoDate.scene_group(dirname)
        formats = format_helper.get(group) if group else []
        _kind, resolved = NfoDate.resolve(text, dirname, formats[0] if formats else None)
        if resolved is not None:
            planned.append((current, resolved.isoformat()))
    return planned


def apply_plan(planned):
    """Writes ORIGINAL_DATE onto every audio file of each planned release."""
    from services.tagger.Song.LabelSong import LabelSong

    counts = Counter()
    for directory, iso_date in planned:
        for name in sorted(os.listdir(directory)):
            if not name.lower().endswith(AUDIO_EXTENSIONS):
                continue
            path = os.path.join(directory, name)
            try:
                song = LabelSong(path)
                existing = song.tag_collection.get_item_as_string(ORIGINAL_DATE)
                if len(existing.replace('-', '')) >= 8:
                    counts['already_precise'] += 1
                    continue
                song.tag_collection.set_item(ORIGINAL_DATE, iso_date)
                song.save_file()
                counts['written'] += 1
            except Exception as exc:  # noqa: BLE001 - one bad file must not stop the backfill
                logging.warning('Could not write %s: %s', path, exc)
                counts['failed'] += 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=DEFAULT_ROOT)
    parser.add_argument('--apply', action='store_true', help='write the tags; default is a dry run')
    args = parser.parse_args(argv)

    from services.common.Helpers.Cache import databaseHelpers

    planned = plan_release_dates(args.root, databaseHelpers['sceneGroupDateFormatHelper'])
    print(f'{len(planned)} releases resolve to a release date')
    if not args.apply:
        for directory, iso_date in planned[:20]:
            print(f'  {iso_date}  {os.path.basename(directory)}')
        print('dry run, nothing written; pass --apply to write the tags')
        return 0
    print(dict(apply_plan(planned)))
    return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    sys.exit(main())
