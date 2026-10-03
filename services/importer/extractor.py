import logging
import os
import re
import shutil
import tempfile
from os import listdir
from os.path import isdir, isfile, join
from typing import Final

import patoolib

from services.common.audio_less_folder import DOCUMENT_EXTENSIONS, IGNORED_NAMES, IMAGE_EXTENSIONS
from services.common.config_store import ConfigStore as Settings
from services.common.Helpers import Quarantine
from services.common.Helpers.ReleaseFolder import AUDIO_EXTENSIONS, is_same_release
from services.importer import conflict_store
from services.importer.conflict_store import FileProblemTracker
from services.importer.settle import STAGING_PREFIX, is_staging

# Backends to try when patool's own choice cannot read an archive. patool picks
# `unrar-free` for RAR in this image, and unrar-free aborts the *whole* archive on the
# first entry whose name it cannot convert to the container locale:
# `Pathname cannot be converted from UTF-16BE to current locale`. One release with
# zero-width spaces in its filenames is enough -- 13 of the 44 releases in
# HC-2026-WEEK-34-MP3.rar landed, the other 31 never did, and because the raise skips
# the quarantine step below the archive was retried and failed again every cycle, forever.
# Setting LANG/LC_ALL in the container does not fix unrar-free; another backend does.
# `unar` reads those names. 7z is the backstop rather than the first choice because
# patool's extract_7z passes `-aou`, so it renames on collision instead of stopping on a
# prompt, while its unar command carries no overwrite flag at all.
FALLBACK_PROGRAMS: Final = ('unar', '7z')

# Suffixes a downloader appends while it is still writing the file: Chrome/Chromium
# (`.crdownload`), Firefox and curl/wget (`.part`), and the generic `.tmp`/`.partial`.
# The muma-firefox container downloads straight into the import folder, so the extract
# step regularly lists a file its writer still owns. patool identifies by *content*, not
# by extension, so a half-written `.rar.crdownload` that already carries a readable RAR
# header extracts truncated and the source is then Quarantine.put out from under the
# writer. The name can also vanish mid-cycle: on 2026-09-16 the run that listed
# `HC-2026-WEEK-37-FLAC.rar.crdownload` at 15:00:08 spent three minutes on an earlier
# entry, and by 15:03:09 the browser had renamed it, so every backend reported `was not
# found`. Skipping these costs nothing -- the next cycle (29-53 min) picks the file up
# under its final name, which is how all four of that evening's archives landed anyway.
# `news.py:180` follows the same convention for the bulletins it writes itself.
IN_FLIGHT_SUFFIXES: Final = ('.crdownload', '.part', '.partial', '.tmp')

# A RAR set split into volumes is extracted from its first volume, which reads the rest
# itself. Two naming schemes exist: `name.part1.rar, name.part2.rar, ...` (any number of
# leading zeros) and the older `name.rar, name.r00, name.r01, ...` running on into
# `.s00` past `.r99`. The other volumes are never extracted on their own -- that only
# fails -- and they are quarantined together with the first once it has been extracted,
# instead of failing again on every cycle for ever.
_PART_VOLUME = re.compile(r'^(?P<base>.+)\.part(?P<number>\d+)\.rar$', re.IGNORECASE)
_OLD_STYLE_VOLUME = re.compile(r'^(?P<base>.+)\.[rs]\d{2}$', re.IGNORECASE)


# What the extract step opens: a file must carry one of these extensions *and* start with
# the matching signature. patool identifies by content and by `file`'s mime guess, and
# answers anything else with "unknown archive mime format" -- after which the step used to
# retry with every fallback backend and fail again on every cycle, forever. Two browser
# downloads of `.mp4` videos in the import folder did exactly that on 2026-09-27: two
# WARNINGs and an ERROR per file per cycle, 218 and 109 of them per file in twelve hours
# (bug report 119). Longest suffixes first, so `.tar.gz` is not read as `.gz`.
_TAR_AT_257 = b'ustar'
_ZIP = (b'PK\x03\x04', b'PK\x05\x06', b'PK\x07\x08')
_RAR = (b'Rar!\x1a\x07',)
_SEVEN_ZIP = (b"7z\xbc\xaf'\x1c",)
_GZIP = (b'\x1f\x8b',)
_BZIP2 = (b'BZh',)
_XZ = (b'\xfd7zXZ\x00',)
ARCHIVE_SIGNATURES: Final[tuple[tuple[str, tuple[bytes, ...]], ...]] = (
    ('.tar.gz', _GZIP),
    ('.tar.bz2', _BZIP2),
    ('.tar.xz', _XZ),
    ('.tgz', _GZIP),
    ('.tbz2', _BZIP2),
    ('.tbz', _BZIP2),
    ('.txz', _XZ),
    ('.tar', ()),
    ('.zip', _ZIP),
    ('.rar', _RAR),
    ('.7z', _SEVEN_ZIP),
)

# Not archives, sorted by what they are so the operator reads "video file" rather than
# "unknown". Audio outside a release folder is its own case: nothing in the pipeline places
# a loose track, so it stands until someone puts it in a folder.
VIDEO_EXTENSIONS: Final = ('.mp4', '.mkv', '.avi', '.mov', '.webm', '.wmv', '.flv', '.m4v', '.mpg', '.mpeg', '.ts')
# Images, documents and the housekeeping files an OS or the NAS drops into any folder
# (IGNORED_NAMES: never an import, never worth a line) are shared with the mover's
# audio-less check, which treats the same kinds as a release's companions.

#: What `classify` returns for a file to extract, and for one to pass over without a word.
ARCHIVE = 'archive'
IGNORE = 'ignore'


def _signature_matches(path: str, signatures: tuple[bytes, ...]) -> bool:
    """Whether the file starts with one of `signatures`; for an empty tuple, a POSIX tar header."""
    with open(path, 'rb') as handle:
        head = handle.read(262)
    if not signatures:
        return head[257:262] == _TAR_AT_257
    return head.startswith(signatures)


def classify(path: str, name: str) -> tuple[str, str]:
    """What an import-folder file is: (ARCHIVE, ''), (IGNORE, ''), or (reason code, detail).

    Only a file with an archive extension whose first bytes carry that archive's signature
    is extracted. Everything else is named by kind, so the one warning and the Beheer row
    say what the file is instead of repeating patool's complaint about it.
    """
    lower = name.lower()
    if lower.startswith('.') or lower in IGNORED_NAMES:
        return IGNORE, ''
    for suffix, signatures in ARCHIVE_SIGNATURES:
        if lower.endswith(suffix):
            try:
                if _signature_matches(path, signatures):
                    return ARCHIVE, ''
            except OSError as e:
                return conflict_store.UNREADABLE, str(e)
            return conflict_store.NOT_AN_ARCHIVE, f'no {suffix} signature at the start of the file'
    if lower.endswith(AUDIO_EXTENSIONS):
        return conflict_store.LOOSE_AUDIO, ''
    if lower.endswith(VIDEO_EXTENSIONS):
        return conflict_store.NOT_MUSIC_VIDEO, ''
    if lower.endswith(IMAGE_EXTENSIONS):
        return conflict_store.NOT_MUSIC_IMAGE, ''
    if lower.endswith(DOCUMENT_EXTENSIONS):
        return conflict_store.NOT_MUSIC_DOCUMENT, ''
    return conflict_store.NOT_MUSIC_OTHER, ''


def is_later_volume(name: str) -> bool:
    """Whether `name` is a RAR volume other than the first, which is never opened itself."""
    part = _PART_VOLUME.match(name)
    if part:
        return int(part.group('number')) != 1
    return bool(_OLD_STYLE_VOLUME.match(name))


def sibling_volumes(name: str, entries: list[str]) -> list[str]:
    """The other volumes of the RAR set whose first volume is `name`, out of `entries`.

    Empty for anything that is not the first volume of a split set, including a plain
    single-file `.rar`.
    """
    part = _PART_VOLUME.match(name)
    if part:
        base = part.group('base').lower()
        return sorted(
            entry
            for entry in entries
            if entry != name
            and (match := _PART_VOLUME.match(entry))
            and match.group('base').lower() == base
            and int(match.group('number')) != 1
        )
    if name.lower().endswith('.rar'):
        base = name[: -len('.rar')].lower()
        return sorted(
            entry
            for entry in entries
            if (match := _OLD_STYLE_VOLUME.match(entry)) and match.group('base').lower() == base
        )
    return []


class Extractor:
    """Unpacks every archive in the import folder, and parks each archive once it has been.

    A file it cannot import -- not an archive, or an archive no backend reads -- is left
    where it is and recorded once in `importer_conflicts` (bug report 119), instead of
    being tried and warned about again on every cycle.
    """

    def __init__(self):
        self.settings = Settings()
        #: The files left in place, so each one is warned about once rather than every cycle.
        self.problems = FileProblemTracker()

    def _attempt(self, file_with_path, program):
        """Extract one archive into a fresh staging folder with one backend.

        Returns the staging folder on success. On a PatoolError the staging folder --
        and whatever part of the archive landed in it -- is removed and the error is
        raised again, so the next backend starts from nothing.
        """
        staging = tempfile.mkdtemp(prefix=STAGING_PREFIX, dir=self.settings.import_folder_path)
        options = {} if program is None else {'program': program}
        try:
            patoolib.extract_archive(file_with_path, outdir=staging, interactive=False, **options)
        except BaseException:
            shutil.rmtree(staging, ignore_errors=True)
            raise
        return staging

    def _extract(self, file_with_path, file) -> tuple[str | None, str, str]:
        """Extract one archive, falling back to another backend when patool's choice fails.

        Each backend extracts into its own staging folder, and only a complete extraction
        is moved into the import folder. Returns `(program, reason, detail)`: on success
        the backend that worked -- the empty string for patool's own default -- and an
        empty reason; otherwise None, the reason code the archive stays on disk for, and
        what went wrong. Nothing is logged above INFO here: the caller records the failure,
        which warns once per archive and not once per cycle.
        """
        failures: list[str] = []
        for program in (None, *FALLBACK_PROGRAMS):
            if failures:
                logging.info('Extraction of %s failed (%s); retrying with %s', file, failures[-1], program)
            try:
                staging = self._attempt(file_with_path, program)
            except patoolib.util.PatoolError as e:
                failures.append(f'{program or "default"}: {e}')
                continue
            try:
                reason, detail = self._move_in(staging, file)
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            if reason:
                return None, reason, detail
            if program:
                logging.info('Extracted %s with %s after the default backend failed', file, program)
            return program or '', '', ''
        return None, conflict_store.EXTRACTION_FAILED, 'every backend failed: ' + '; '.join(failures)

    def _move_in(self, staging, file) -> tuple[str, str]:
        """Move a complete extraction from its staging folder into the import folder.

        Nothing is moved unless everything can be. An entry whose name is already taken
        by the same release -- an earlier extraction of the same archive, say -- is
        dropped from the staging copy; a name taken by anything else leaves the archive
        where it is for a human, rather than merging two releases into one folder.
        Returns `('', '')` when everything was moved, else the reason code and detail.
        """
        import_folder = self.settings.import_folder_path
        entries = sorted(listdir(staging))
        if not entries:
            return conflict_store.EXTRACTION_EMPTY, ''
        to_move = []
        for entry in entries:
            target = join(import_folder, entry)
            if not os.path.lexists(target):
                to_move.append(entry)
            elif isdir(target) and isdir(join(staging, entry)) and is_same_release(join(staging, entry), target):
                logging.info('%s from %s is already in the import folder; keeping the copy there', entry, file)
            else:
                return conflict_store.EXTRACTION_NAME_TAKEN, f'{entry} already exists in the import folder'
        for entry in to_move:
            shutil.move(join(staging, entry), join(import_folder, entry))
        return '', ''

    def _sweep_staging(self):
        """Remove staging folders a killed run left behind; none of them is a finished extraction."""
        for entry in listdir(self.settings.import_folder_path):
            path = join(self.settings.import_folder_path, entry)
            if is_staging(entry) and isdir(path):
                logging.warning('Removing %s, left behind by an extraction that never finished', path)
                shutil.rmtree(path, ignore_errors=True)

    def run(self, dry_run=False):
        """Extract every archive in the import folder and quarantine it afterwards.

        A file that is not an archive, or an archive that cannot be extracted, stays where
        it is and is recorded once (bug report 119); on later cycles it is skipped without
        being opened, until it changes on disk or disappears.
        """
        logging.info('Starting Extract Step')
        try:
            if not dry_run:
                self._sweep_staging()
            entries = [
                f
                for f in listdir(self.settings.import_folder_path)
                if isfile(join(self.settings.import_folder_path, f))
            ]
            in_flight = [f for f in entries if f.endswith(IN_FLIGHT_SUFFIXES)]
            complete = [f for f in entries if not f.endswith(IN_FLIGHT_SUFFIXES)]
            only_files = [f for f in complete if not is_later_volume(f)]
            if in_flight:
                logging.info(f'Skipping {len(in_flight)} download(s) still in flight: {in_flight}')
            logging.info(f'Found {len(only_files)} files: {only_files}')
        except Exception as e:
            logging.error(f'Failed to list files: {e}')
            return
        arriving = [f[: -len(suffix)] for f in in_flight for suffix in IN_FLIGHT_SUFFIXES if f.endswith(suffix)]
        self.problems.begin()
        for idx, file in enumerate(only_files, start=1):
            try:
                file_with_path = join(self.settings.import_folder_path, file)
                if self.problems.standing(file_with_path):
                    continue
                kind, detail = classify(file_with_path, file)
                if kind == IGNORE:
                    continue
                if kind != ARCHIVE:
                    self.problems.problem(file_with_path, kind, detail, dry_run=dry_run)
                    continue
                volumes = sibling_volumes(file, complete)
                if sibling_volumes(file, arriving):
                    logging.info(f'[{idx}/{len(only_files)}] Waiting for the rest of the volumes of {file}')
                    continue
                if dry_run:
                    logging.info(f'[{idx}/{len(only_files)}] Dry run - would extract: {file_with_path}')
                    continue
                logging.info(f'[{idx}/{len(only_files)}] Extracting: {file_with_path}')
                program, reason, detail = self._extract(file_with_path, file)
                if program is None:
                    # A taken name is resolved beside the archive, not in it: look again
                    # once the import folder itself changed.
                    watch = reason == conflict_store.EXTRACTION_NAME_TAKEN
                    self.problems.problem(file_with_path, reason, detail, watch_folder=watch)
                    continue
                # Parked, not removed. Extraction succeeding says nothing about the
                # release surviving the rest of the pipeline -- the renamer and mover
                # both still have to place it -- and for a label rip this archive is the
                # only pristine copy of the release there will ever be. Quarantine.sweep
                # takes it away once the retention window closes.
                logging.info(f'[{idx}/{len(only_files)}] Quarantining: {file_with_path}')
                Quarantine.put(file_with_path, Quarantine.EXTRACTED_ARCHIVE)
                for volume in volumes:
                    Quarantine.put(join(self.settings.import_folder_path, volume), Quarantine.EXTRACTED_ARCHIVE)
            except OSError as e:
                error_msg = f'Failed to move {file} out of the import folder: {e}'
                logging.error(error_msg)
            except Exception as e:
                error_msg = f'Unexpected error with {file}: {e}'
                logging.error(error_msg)
        self.problems.end(dry_run=dry_run)
        logging.info('Extraction step completed.')
