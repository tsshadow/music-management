"""Repairs the label of tracks that were tagged from the wrong folder.

A release that shipped a second copy of its own folder inside itself put the audio one level
below `<eps root>/<label>/<release>/`. The tagger counted parents up from the file, so the
release folder became the label: `ABSLT065 - Hartshorn_-_LOSE_CTRL-(ABSLT065)-SINGLE-WEB-2026-SRG`
instead of `ABSLT Records`. The tagger now anchors on the EPs root, but the tracks already on disk
keep the wrong publisher, catalog number and copyright until they are rewritten.

The check is the same for every file under the root, so a file that was flattened after it was
tagged is repaired as well - its path no longer shows what went wrong, only its tags do.
Dry run by default: it reports what it would write before anything touches a file.
"""
import argparse
import errno
import json
import logging
import os
import re
import sys
import time
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

from services.tagger.Song import LabelPath

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.aac', '.wav')
DEFAULT_ROOT = '/mnt/music/EPs'
RETRY_DELAYS = (2, 8, 30)


def with_retries(work, path, delays=RETRY_DELAYS, sleep=time.sleep):
    """Runs `work()`, waiting out a refusal that is really a file still being written.

    `path` only names the file in the log.

    The import workers write into the same share, and opening a file another process holds is a
    sharing violation that SMB reports as `[Errno 13] Permission denied` - the same errno a real
    permission wall gives. Here it is temporary: every one of the files a first pass was refused
    read fine minutes later. Treating it as terminal silently drops those files from the plan, so
    it is waited out instead, and only a refusal that outlives every delay is reported.
    """
    for delay in delays:
        try:
            return work()
        except OSError as exc:
            if exc.errno != errno.EACCES:
                raise
            logging.info('Refused, retrying in %ss: %s', delay, path)
            sleep(delay)
    return work()


def audio_files(root):
    """Every audio file under the root, minus Synology's @eaDir and the `_` folders.

    A label folder starting with `_` is parsed as a generic song, not as a label release, so its
    tracks never carried a path derived publisher and must not gain one here.
    """
    for current, dirs, files in os.walk(root):
        dirs[:] = sorted(d for d in dirs if d != '@eaDir')
        if os.path.relpath(current, root).split(os.sep, maxsplit=1)[0].startswith('_'):
            continue
        for name in sorted(files):
            if name.lower().endswith(AUDIO_EXTENSIONS):
                yield os.path.join(current, name)


def looks_like_the_release_folder(publisher, path, root):
    """Whether the publisher a file carries is really the name of its own release folder.

    This is the guard that keeps the backfill to the bug at hand. Any other disagreement between
    a track and its label folder - a hand corrected publisher, a track filed under a label it was
    not tagged for - is left for a human, because a folder name is not evidence that the tag is
    wrong. A flattened release no longer has the inner folder in its path, so the release folder
    containing the publisher counts too: the inner copy was the outer name minus the catalog
    number prefix.
    """
    if not publisher:
        return False
    _label, release_folder = LabelPath.split(path, root, os.sep)
    below_the_label = os.path.relpath(path, root).split(os.sep)[1:-1]
    return publisher in below_the_label or publisher in release_folder


def plan_fix(path, root, tags):
    """The tags to rewrite for one file, or `None` when there is nothing to repair.

    `tags` holds the publisher, catalognumber, copyright and date the file carries today.
    """
    label, release_folder = LabelPath.split(path, root, os.sep)
    if not label:
        return None
    changes = {}
    publisher = (tags.get('publisher') or '').strip()
    if publisher != label and looks_like_the_release_folder(publisher, path, root):
        changes['publisher'] = label
        catalog_number = LabelPath.catalog_number(release_folder)
        if catalog_number and (tags.get('catalognumber') or '').strip() != catalog_number:
            changes['catalognumber'] = catalog_number
    # The copyright the tagger derives is the publisher plus the year, and it only ever writes one
    # when the file has none. A release that was flattened and retagged therefore has a correct
    # publisher again while its copyright still names the release folder: that one survives every
    # further tagger run and has to be repaired here too.
    copyright_tag = (tags.get('copyright') or '').strip()
    holder, year = split_copyright(copyright_tag)
    repairable = looks_like_the_release_folder(holder, path, root) or (
        changes and not copyright_tag
    )
    if repairable and holder != label:
        year = str(tags.get('date') or '')[:4] or year
        changes['copyright'] = f'{label} ({year})' if year else label
    return changes or None


def split_copyright(copyright_tag):
    """`(holder, year)` for a copyright the tagger wrote, which reads `<publisher> (<year>)`."""
    match = re.match(r'^(.*?)\s*\((\d{4})\)$', copyright_tag)
    if match:
        return (match.group(1), match.group(2))
    return (copyright_tag, '')


def open_song(path):
    """A `BaseSong` for the file, without letting a broken m4a be deleted on the way in.

    `BaseSong` removes an m4a whose stream will not load - that is the tagger's own cleanup of a
    half finished download. A backfill is not the place for it, so an m4a is loaded once by hand
    first and a broken one is reported as unreadable instead.
    """
    from mutagen.mp4 import MP4, MP4StreamInfoError

    from services.tagger.Song.BaseSong import BaseSong

    if path.lower().endswith('.m4a'):
        try:
            MP4(path)
        except MP4StreamInfoError as exc:
            raise OSError(f'unreadable m4a: {exc}') from exc
    return BaseSong(path)


def read_tags(path):
    """The publisher, catalog number, copyright and date one file carries, via the tagger."""
    from services.tagger.constants import CATALOG_NUMBER, COPYRIGHT, DATE, PUBLISHER

    song = open_song(path)
    return {
        'publisher': song.tag_collection.get_item_as_string(PUBLISHER),
        'catalognumber': song.tag_collection.get_item_as_string(CATALOG_NUMBER),
        'copyright': song.tag_collection.get_item_as_string(COPYRIGHT),
        'date': song.tag_collection.get_item_as_string(DATE),
    }


def label_folders(root, after=None):
    """The label folders to scan, skipping the `_` ones the tagger parses as generic songs.

    `after` resumes an interrupted pass: the folders are always walked in the same order, so the
    name of the last one reported is enough to say where to pick up.
    """
    names = sorted(
        name for name in os.listdir(root)
        if not name.startswith('_') and os.path.isdir(os.path.join(root, name))
    )
    return [name for name in names if name > after] if after else names


def load_plan(path):
    """A plan written by an earlier run: one object per line, or one array written in one go."""
    with open(path, encoding='utf-8') as handle:
        text = handle.read().strip()
    if text.startswith('['):
        return [tuple(entry) for entry in json.loads(text)]
    entries = [json.loads(line) for line in text.splitlines() if line.strip()]
    return [(entry['path'], entry['changes']) for entry in entries]


def plan_all(root, workers=16, labels=None, plan_handle=None):
    """`[(path, changes)]` for every file whose label tags disagree with its label folder.

    One label folder at a time: over a network share, walking the whole tree before reading the
    first tag means a quarter of an hour of silence, and a run that is interrupted has nothing to
    show for it. Per label the walk and the reads interleave and every label reports as it lands.

    A full pass takes hours, so each label's findings are flushed to `plan_handle` as they land -
    one JSON object per line. An interrupted run keeps everything up to the last label reported,
    and `--resume-after` starts the next one where it stopped.
    """
    counts = Counter()
    planned = []
    unreadable = []

    def inspect(path):
        try:
            changes = plan_fix(path, root, with_retries(lambda: read_tags(path), path))
            return (path, changes) if changes else None
        except Exception as exc:  # noqa: BLE001 - one unreadable file must not stop the scan
            # A file that is still refused after every retry is simply not in the plan, so the run
            # keeps the list and reports it rather than leaving it in the log.
            logging.warning('Could not read %s: %s', path, exc)
            unreadable.append(path)
            counts['unreadable'] += 1
            return None

    with ThreadPoolExecutor(max_workers=workers) as executor:
        for label in labels or label_folders(root):
            files = list(audio_files(os.path.join(root, label)))
            found = [result for result in executor.map(inspect, files) if result]
            counts['read'] += len(files)
            planned.extend(found)
            if plan_handle:
                for entry_path, changes in found:
                    plan_handle.write(json.dumps({'path': entry_path, 'changes': changes}) + '\n')
                plan_handle.flush()
            logging.info('%-40s %5d files, %4d to fix', label[:40], len(files), len(found))
    return planned, counts, unreadable


def apply_plan(planned):
    """Writes the planned tags onto each file."""
    from services.tagger.constants import CATALOG_NUMBER, COPYRIGHT, PUBLISHER

    tag_names = {'publisher': PUBLISHER, 'catalognumber': CATALOG_NUMBER, 'copyright': COPYRIGHT}
    counts = Counter()
    def write(path, changes):
        song = open_song(path)
        for key, value in changes.items():
            song.tag_collection.set_item(tag_names[key], value)
        song.save_file()

    for path, changes in planned:
        try:
            # A write lands mid import just as easily as a read does, and is refused the same way.
            with_retries(lambda file=path, tags=changes: write(file, tags), path)
            counts['written'] += 1
        except Exception as exc:  # noqa: BLE001 - one bad file must not stop the backfill
            logging.warning('Could not write %s: %s', path, exc)
            counts['failed'] += 1
    return counts


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', default=DEFAULT_ROOT)
    parser.add_argument('--label', action='append', help='scan only this label folder; repeatable')
    parser.add_argument('--workers', type=int, default=16)
    parser.add_argument('--plan-file', help='append the plan here, to apply it without rescanning')
    parser.add_argument('--resume-after', help='start at the label folder after this one')
    parser.add_argument('--from-plan', help='apply a plan written earlier instead of scanning')
    parser.add_argument('--apply', action='store_true', help='write the tags; default is a dry run')
    args = parser.parse_args(argv)

    if args.from_plan:
        planned = load_plan(args.from_plan)
        counts, unreadable = Counter(read=0, unreadable=0), []
    else:
        labels = args.label or label_folders(args.root, args.resume_after)
        # Appended, never truncated: a resumed pass has to add to what the interrupted one found.
        with open(args.plan_file or os.devnull, 'a', encoding='utf-8') as handle:
            planned, counts, unreadable = plan_all(args.root, args.workers, labels, handle)
    if args.plan_file and unreadable:
        # The refused files are the ones the plan cannot speak for, so they are written down next
        # to it: `--label` re-runs them once whatever held them has let go.
        with open(args.plan_file + '.unreadable', 'a', encoding='utf-8') as handle:
            handle.write('\n'.join(unreadable) + '\n')
    print(f'{counts["read"]} files read, {counts["unreadable"]} unreadable, {len(planned)} to fix')
    print(dict(Counter(key for _path, changes in planned for key in changes)))
    labels = Counter(os.path.relpath(path, args.root).split(os.sep, maxsplit=1)[0] for path, _c in planned)
    for label, number in labels.most_common(25):
        print(f'  {number:5d}  {label}')
    if not args.apply:
        for path, changes in planned[:10]:
            print(f'  {path}\n    {changes}')
        print('dry run, nothing written; pass --apply to write the tags')
        return 0
    print(dict(apply_plan(planned)))
    return 0


if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    sys.exit(main())
