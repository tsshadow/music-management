import logging
import os
import re
import shutil
import tempfile
from os import listdir
from os.path import isdir, isfile, join
from typing import Final

import patoolib

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers import Quarantine
from services.common.Helpers.ReleaseFolder import is_same_release
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
    """Unpacks every archive in the import folder, and parks each archive once it has been."""

    def __init__(self):
        self.settings = Settings()

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

    def _extract(self, file_with_path, file):
        """Extract one archive, falling back to another backend when patool's choice fails.

        Each backend extracts into its own staging folder, and only a complete extraction
        is moved into the import folder. Returns the backend that succeeded -- the empty
        string for patool's own default -- or None when every backend failed, or the
        result could not be placed, and the archive has to stay on disk.
        """
        failures: list[str] = []
        for program in (None, *FALLBACK_PROGRAMS):
            if failures:
                logging.warning('Extraction of %s failed (%s); retrying with %s', file, failures[-1], program)
            try:
                staging = self._attempt(file_with_path, program)
            except patoolib.util.PatoolError as e:
                failures.append(f'{program or "default"}: {e}')
                continue
            try:
                if not self._move_in(staging, file):
                    return None
            finally:
                shutil.rmtree(staging, ignore_errors=True)
            if program:
                logging.info('Extracted %s with %s after the default backend failed', file, program)
            return program or ''
        logging.error('Extraction failed for %s with every backend (%s)', file, '; '.join(failures))
        return None

    def _move_in(self, staging, file) -> bool:
        """Move a complete extraction from its staging folder into the import folder.

        Nothing is moved unless everything can be. An entry whose name is already taken
        by the same release -- an earlier extraction of the same archive, say -- is
        dropped from the staging copy; a name taken by anything else leaves the archive
        where it is for a human, rather than merging two releases into one folder.
        """
        import_folder = self.settings.import_folder_path
        entries = sorted(listdir(staging))
        if not entries:
            logging.error('Extraction of %s produced nothing; leaving the archive in place', file)
            return False
        to_move = []
        for entry in entries:
            target = join(import_folder, entry)
            if not os.path.lexists(target):
                to_move.append(entry)
            elif isdir(target) and isdir(join(staging, entry)) and is_same_release(join(staging, entry), target):
                logging.info('%s from %s is already in the import folder; keeping the copy there', entry, file)
            else:
                logging.warning(
                    'Not extracting %s: %s already exists in the import folder and differs from the archive. '
                    'Leaving the archive in place for manual intervention',
                    file,
                    entry,
                )
                return False
        for entry in to_move:
            shutil.move(join(staging, entry), join(import_folder, entry))
        return True

    def _sweep_staging(self):
        """Remove staging folders a killed run left behind; none of them is a finished extraction."""
        for entry in listdir(self.settings.import_folder_path):
            path = join(self.settings.import_folder_path, entry)
            if is_staging(entry) and isdir(path):
                logging.warning('Removing %s, left behind by an extraction that never finished', path)
                shutil.rmtree(path, ignore_errors=True)

    def run(self, dry_run=False):
        """Extract every settled archive in the import folder and quarantine it afterwards."""
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
        for idx, file in enumerate(only_files, start=1):
            try:
                file_with_path = join(self.settings.import_folder_path, file)
                volumes = sibling_volumes(file, complete)
                if sibling_volumes(file, arriving):
                    logging.info(f'[{idx}/{len(only_files)}] Waiting for the rest of the volumes of {file}')
                    continue
                if dry_run:
                    logging.info(f'[{idx}/{len(only_files)}] Dry run - would extract: {file_with_path}')
                    continue
                logging.info(f'[{idx}/{len(only_files)}] Extracting: {file_with_path}')
                if self._extract(file_with_path, file) is None:
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
            except patoolib.util.PatoolError as e:
                error_msg = f'Extraction failed for {file}: {e}'
                logging.error(error_msg)
            except OSError as e:
                error_msg = f'Failed to move {file} out of the import folder: {e}'
                logging.error(error_msg)
            except Exception as e:
                error_msg = f'Unexpected error with {file}: {e}'
                logging.error(error_msg)
        logging.info('Extraction step completed.')
