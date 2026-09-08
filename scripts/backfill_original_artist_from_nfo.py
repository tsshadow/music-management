"""Restores the artist wording the tagger split away, from the NFO that shipped with the release.

`CleanTagsRule` turns "Eternate & Prosphere" into two values and drops the "&". Since 0.47 it keeps
the original in `TXXX:ORIGINAL_ARTIST` when it does that -- but only at the moment it splits. A file
that was already split has nothing left to capture, so a re-tag can never fill it in: measured over
400 files under the EPs root, 120 carry a split artist and *none* still carry the original wording.
The NFO inside the release directory is written before any of that and still says it.

The guard that makes this safe: a line is only used when splitting its artist with the tagger's own
rule yields exactly the artists the file already holds. A write can then only restore wording -- it
cannot introduce, drop or rename an artist. Anything that disagrees is skipped rather than guessed
at, and nothing that already has an ORIGINAL_ARTIST is touched.

Only the EPs tree has NFOs; Soundcloud, Youtube and artists have none, so they are out of scope by
construction rather than by choice.

Dry run by default: it reports what it would write before anything touches a file.
"""

import argparse
import logging
import os
import re
import sys
from collections import Counter
from concurrent.futures import ThreadPoolExecutor

from dotenv import load_dotenv

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# mutagen is imported inside the two functions that touch a file rather than here. The unit suite
# replaces the whole package with a stub (services/tests/mock_base.py), and a submodule import at
# module level fails there before a single test runs -- while the planning logic these tests cover
# needs no mutagen at all.

from scripts.backfill_label_from_path import is_refusal, with_retries  # noqa: E402
from services.tagger.Song.NfoDate import read_nfo  # noqa: E402
from services.tagger.Song.NfoTracklist import entries, restorable_wording  # noqa: E402

load_dotenv(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), '.env'))

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.opus', '.wav')
DEFAULT_ROOT = '/mnt/music/EPs'
TAG_NAME = 'ORIGINAL_ARTIST'

logger = logging.getLogger('backfill_original_artist')

# The leading track number of a scene filename: "01_artist_-_title.mp3", "03-artist-title.mp3",
# "101_..." on a multi-disc rip. The disc digit is kept: it is matched against the NFO's own
# numbering, which carries it too when the release is multi-disc.
_FILE_NUMBER = re.compile(r'^(\d{1,3})[\s_\-\.]')


def file_number(name):
    """The track number a filename leads with, or None."""
    match = _FILE_NUMBER.match(name)
    return int(match.group(1)) if match else None


def audio_files(directory):
    """`{number: path}` for the audio in one release directory.

    A number claimed by two files is dropped rather than guessed at -- that is a multi-disc rip
    numbered per disc, and picking either file would be a coin toss.
    """
    try:
        names = sorted(n for n in os.listdir(directory) if n.lower().endswith(AUDIO_EXTENSIONS))
    except OSError as exc:
        logger.debug('No listing for %s: %s', directory, exc)
        return {}
    by_number = {}
    duplicates = set()
    for name in names:
        number = file_number(name)
        if number is None:
            continue
        if number in by_number:
            duplicates.add(number)
            continue
        by_number[number] = os.path.join(directory, name)
    for number in duplicates:
        by_number.pop(number, None)
    return by_number


def read_artist_state(path):
    """`(artist values, existing original artist)` read straight off the file.

    Deliberately not through `ReadonlySong`: that constructor deletes an m4a it cannot parse and
    rewrites a FLAC whose tag keys are lower case, neither of which a backfill should ever trigger.
    """
    import mutagen
    from mutagen.id3 import ID3

    audio = mutagen.File(path, easy=False)
    if audio is None or audio.tags is None:
        return ([], None)
    tags = audio.tags
    values, original = [], None
    if isinstance(tags, ID3) or hasattr(tags, 'getall'):
        frames = tags.getall('TPE1')
        values = [str(v) for frame in frames for v in frame.text]
        for frame in tags.getall('TXXX'):
            if (frame.desc or '').upper() == TAG_NAME:
                original = '; '.join(str(v) for v in frame.text)
    else:  # vorbis comments and mp4 atoms both behave like a mapping
        for key in ('ARTIST', 'artist', '\xa9ART'):
            if key in tags:
                values = [str(v) for v in tags[key]]
                break
        for key in (TAG_NAME, TAG_NAME.lower(), f'----:com.apple.iTunes:{TAG_NAME}'):
            if key in tags:
                raw = tags[key]
                original = '; '.join(v.decode('utf-8', 'replace') if isinstance(v, bytes) else str(v) for v in raw)
                break
    # A single ID3 frame may itself hold the joined form the tagger writes.
    if len(values) == 1 and ';' in values[0]:
        values = [part.strip() for part in values[0].split(';') if part.strip()]
    return (values, original)


def write_original_artist(path, value):
    """Write ORIGINAL_ARTIST in whatever the format's own spelling of it is.

    The targets mirror `services/tagger/constants.py`, so the scanner reads back exactly what the
    tagger would have written: a `TXXX:ORIGINAL_ARTIST` frame on ID3, a plain uppercase comment on
    FLAC and Opus, and the iTunes freeform atom on MP4 -- which is why MP4Tags deliberately leaves
    this field unmapped.
    """
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3, TXXX
    from mutagen.mp4 import MP4, MP4FreeForm
    from mutagen.oggopus import OggOpus

    extension = os.path.splitext(path)[1].lower()
    if extension in ('.mp3', '.wav'):
        tags = ID3(path)
        tags.delall(f'TXXX:{TAG_NAME}')
        tags.add(TXXX(encoding=3, desc=TAG_NAME, text=[value]))
        tags.save(path)
    elif extension == '.flac':
        audio = FLAC(path)
        audio[TAG_NAME] = [value]
        audio.save()
    elif extension == '.opus':
        audio = OggOpus(path)
        audio[TAG_NAME] = [value]
        audio.save()
    elif extension == '.m4a':
        audio = MP4(path)
        audio.tags[f'----:com.apple.iTunes:{TAG_NAME}'] = [MP4FreeForm(value.encode('utf-8'))]
        audio.save()
    else:
        raise ValueError(f'no ORIGINAL_ARTIST mapping for {extension}')


def plan_release(directory):
    """`([(path, wording)], counter)` for one release directory."""
    counts = Counter()
    text = read_nfo(directory)
    if not text:
        counts['no_nfo'] += 1
        return ([], counts)
    listed = entries(text)
    if not listed:
        counts['no_tracklist'] += 1
        return ([], counts)
    by_number = audio_files(directory)
    if not by_number:
        counts['no_numbered_audio'] += 1
        return ([], counts)

    numbered = [(number, artist) for number, artist, _title in listed if number is not None]
    headers = [artist for number, artist, _title in listed if number is None]
    # A single's NFO states the release once instead of listing it; that one line then speaks for
    # the one track in the directory, and for nothing else.
    if not numbered and len(headers) == 1 and len(by_number) == 1:
        numbered = [(next(iter(by_number)), headers[0])]

    planned = []
    for number, nfo_artist in numbered:
        path = by_number.get(number)
        if not path:
            counts['no_file_for_line'] += 1
            continue
        counts['considered'] += 1
        try:
            values, existing = with_retries(lambda p=path: read_artist_state(p), path)
        except Exception as exc:  # noqa: BLE001 - reported, never fatal for the run
            counts['unreadable'] += 1
            logger.debug('Unreadable %s: %s', path, exc)
            continue
        if existing:
            counts['already_has_original'] += 1
            continue
        wording = restorable_wording(nfo_artist, values)
        if not wording:
            counts['nothing_to_restore'] += 1
            continue
        planned.append((path, wording))
        counts['to_write'] += 1
    return (planned, counts)


def release_dirs(root, labels=None, resume_after=None):
    """Every `<root>/<label>/<release>` directory, in a stable order."""
    try:
        found = sorted(d for d in os.listdir(root) if os.path.isdir(os.path.join(root, d)))
    except OSError as exc:
        logger.error('Cannot list %s: %s', root, exc)
        return []
    if labels:
        found = [d for d in found if d in set(labels)]
    if resume_after:
        found = [d for d in found if d > resume_after]
    for label in found:
        label_dir = os.path.join(root, label)
        try:
            releases = sorted(d for d in os.listdir(label_dir) if os.path.isdir(os.path.join(label_dir, d)))
        except OSError as exc:
            logger.debug('Cannot list %s: %s', label_dir, exc)
            continue
        for release in releases:
            yield os.path.join(label_dir, release)


def plan_all(root, workers, labels, resume_after, plan_handle):
    planned, counts = [], Counter()
    directories = list(release_dirs(root, labels, resume_after))
    logger.info('%d release directories to inspect', len(directories))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for index, (rows, sub) in enumerate(pool.map(plan_release, directories), start=1):
            counts.update(sub)
            for path, wording in rows:
                planned.append((path, wording))
                plan_handle.write(f'{wording}\t{path}\n')
            if index % 500 == 0:
                logger.info('%d/%d directories, %d to write', index, len(directories), len(planned))
    return (planned, counts)


def load_plan(plan_path):
    rows = []
    with open(plan_path, encoding='utf-8') as handle:
        for line in handle:
            wording, _tab, path = line.rstrip('\n').partition('\t')
            if path:
                rows.append((path, wording))
    return rows


def still_restorable(path, wording):
    """Whether the guard that planned this row still holds for the file as it is right now.

    The plan is a snapshot. Walking the whole tree takes hours and the plan is then applied later
    still, while the tagger keeps writing to the same files -- so by the time a row is written its
    file may have gained an ORIGINAL_ARTIST of its own, or a different artist list that this wording
    no longer describes. Writing it anyway would clobber a fresher credit or state a wrong one, the
    two things `plan_release` exists to prevent. `restorable_wording` is idempotent on a wording it
    produced, so re-asking it is the same question the plan asked, put again to today's file.
    """
    values, existing = read_artist_state(path)
    if existing:
        return 'skipped_gained_original'
    if restorable_wording(wording, values) != wording:
        return 'skipped_artists_changed'
    return None


def apply_plan(planned, failed_path=None):
    counts, failed = Counter(), []
    for path, wording in planned:
        try:
            skipped = with_retries(lambda p=path, w=wording: still_restorable(p, w), path)
            if skipped:
                counts[skipped] += 1
                continue
            with_retries(lambda p=path, w=wording: write_original_artist(p, w), path)
            counts['written'] += 1
        except Exception as exc:  # noqa: BLE001 - a refused file must not stop the run
            counts['refused' if is_refusal(exc) else 'failed'] += 1
            failed.append((path, wording))
            logger.warning('Could not write %s: %s', path, exc)
    if failed_path and failed:
        # Written in the plan's own format, so the file it leaves behind is one `--from-plan` can
        # replay once the refusal is lifted. A bare list of paths cannot be replayed: the wording
        # to write lives nowhere else.
        with open(failed_path, 'a', encoding='utf-8') as handle:
            handle.write(''.join(f'{wording}\t{path}\n' for path, wording in failed))
    return (counts, failed)


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
        planned, counts = load_plan(args.from_plan), Counter()
    else:
        with open(args.plan_file or os.devnull, 'a', encoding='utf-8') as handle:
            planned, counts = plan_all(args.root, args.workers, args.label, args.resume_after, handle)

    print(f'{len(planned)} files would get an ORIGINAL_ARTIST')
    for key, value in sorted(counts.items()):
        print(f'  {key:<22} {value}')
    if not args.apply:
        for path, wording in planned[:15]:
            print(f'  {wording}\n    {os.path.basename(path)}')
        print('dry run, nothing written; pass --apply to write the tags')
        return 0
    written, failed = apply_plan(planned, (args.plan_file + '.failed') if args.plan_file else None)
    print(f'{written["written"]} written, {written["refused"]} refused, {written["failed"]} failed')
    if failed:
        print(f'{len(failed)} files could not be written; re-run them with --from-plan once freed')
    return 0


if __name__ == '__main__':
    # `Tag.regex()` reports every split it makes on the *root* logger, and the guard splits an NFO
    # line for every track it considers. At INFO that is one line per track across the whole tree,
    # burying the progress this script reports. So the root stays at WARNING and this script's own
    # logger is the one turned up.
    logging.basicConfig(level=logging.WARNING, format='%(asctime)s %(levelname)s %(message)s')
    logger.setLevel(logging.INFO)
    sys.exit(main())
