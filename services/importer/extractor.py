import logging
from os import listdir
from os.path import isfile, join
from typing import Final

import patoolib

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers import Quarantine

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


class Extractor:
    def __init__(self):
        self.settings = Settings()

    def _extract(self, file_with_path, file):
        """Extract one archive, falling back to another backend when patool's choice fails.

        Returns the backend that succeeded -- the empty string for patool's own default --
        or None when every backend failed and the archive has to stay on disk.
        """
        try:
            patoolib.extract_archive(file_with_path, outdir=self.settings.import_folder_path, interactive=False)
            return ''
        except patoolib.util.PatoolError as e:
            failures = [f'default: {e}']
        for program in FALLBACK_PROGRAMS:
            logging.warning('Extraction of %s failed (%s); retrying with %s', file, failures[-1], program)
            try:
                patoolib.extract_archive(
                    file_with_path,
                    outdir=self.settings.import_folder_path,
                    interactive=False,
                    program=program,
                )
                logging.info('Extracted %s with %s after the default backend failed', file, program)
                return program
            except patoolib.util.PatoolError as e:
                failures.append(f'{program}: {e}')
        logging.error('Extraction failed for %s with every backend (%s)', file, '; '.join(failures))
        return None

    def run(self, dry_run=False):
        logging.info('Starting Extract Step')
        try:
            entries = [
                f
                for f in listdir(self.settings.import_folder_path)
                if isfile(join(self.settings.import_folder_path, f))
            ]
            only_files = [f for f in entries if not f.endswith(IN_FLIGHT_SUFFIXES)]
            in_flight = [f for f in entries if f.endswith(IN_FLIGHT_SUFFIXES)]
            if in_flight:
                logging.info(f'Skipping {len(in_flight)} download(s) still in flight: {in_flight}')
            logging.info(f'Found {len(only_files)} files: {only_files}')
        except Exception as e:
            logging.error(f'Failed to list files: {e}')
            return
        for idx, file in enumerate(only_files, start=1):
            try:
                file_with_path = join(self.settings.import_folder_path, file)
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
