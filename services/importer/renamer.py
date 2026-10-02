import errno
import logging
import os
from os import listdir
from os.path import isdir, isfile, join

from services.common.catalogue_number import from_folder_name
from services.common.config_store import ConfigStore as Settings
from services.common.Helpers import Quarantine
from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.importer.conflict_store import RENAMER, ConflictTracker
from services.importer.release_compare import is_same_release
from services.importer.release_info import ReleaseInfo
from services.importer.settle import is_settled, is_staging


def has_numbers(input_string):
    """Whether `input_string` contains a digit."""
    return any(char.isdigit() for char in input_string)


def is_parsed(folder):
    """Whether `folder` already has the 'Artist - Title' shape."""
    return '- ' in folder


def find_cat_id(folder):
    """`folder` prefixed with its catalogue number, or None when its name carries none.

    The catalogue number is the last parenthesised group that `is_catalogue_number`
    accepts. A folder without one keeps its name: the empty ` - ` prefix this used to
    give it, and the word prefix of a festival anthem (`Official_Hardbass_2026_Anthem -
    ...`), told the Mover nothing and hid the real name (bug report 145).
    """
    catalogue_number = from_folder_name(folder)
    if catalogue_number is None:
        return None
    return catalogue_number + ' - ' + folder


class Renamer:
    """Prefixes every release folder in the import folder with the catalogue number its name carries.

    A folder whose name carries none gets the catalogue number its .nfo states, if that is a
    real one (docs/designs/release-info-enrichment/), and is otherwise left as it is (bug
    report 145).
    """

    def __init__(self, release_info: ReleaseInfo | None = None):
        self.settings = Settings()
        #: The .nfo facts per folder, shared with the Mover so each .nfo is read once.
        self.release_info = release_info or ReleaseInfo()
        #: Standing conflicts, so each one is warned about once rather than every cycle.
        self.conflicts = ConflictTracker(RENAMER)

    def run(self, dry_run=False):
        """Rename every release folder that needs it; `dry_run` only logs what would happen."""
        logging.info('Starting Rename Step')
        self.conflicts.begin()
        only_folders = [
            f
            for f in listdir(self.settings.import_folder_path)
            if not isfile(join(self.settings.import_folder_path, f))
        ]
        for folder in only_folders:
            if '@eaDir' in folder:
                logging.info('skipping @eaDir')
            elif is_staging(folder):
                continue
            elif not is_parsed(folder):
                new_name = find_cat_id(folder) or self._from_nfo(folder)
                if new_name is None:
                    # Nothing to put in front. Asked before the settle check, which walks
                    # the whole folder over CIFS, because a folder without a catalogue
                    # number now keeps its name and is met again every cycle.
                    continue
                # Renaming a folder a copy is still filling sends the rest of the copy
                # into a fresh folder under the old name.
                if not is_settled(join(self.settings.import_folder_path, folder)):
                    continue
                logging.info('input: %s', folder)
                logging.info('parsed: %s', new_name)
                if dry_run:
                    logging.info('Dry run - would rename: %s -> %s', folder, new_name)
                    continue
                try:
                    src = self.settings.import_folder_path + self.settings.delimiter + folder
                    dst = self.settings.import_folder_path + self.settings.delimiter + new_name
                    os.rename(src, dst)
                    # The import folder lives inside the library (/mnt/music/EPs/__TODO), so
                    # LMS has both of these in its index and needs to hear about the rename.
                    lms_scan_trigger.notify([src, dst])
                except OSError as e:
                    # ENOTEMPTY is the one that kept a duplicate download in the import folder
                    # forever: os.rename onto an existing *non-empty* directory raises a plain
                    # OSError(39), which is not a FileExistsError, so this used to fall through to
                    # the generic handler below, be logged at INFO and be retried every cycle.
                    # EEXIST is the same collision on filesystems that report it that way.
                    if e.errno in (errno.ENOTEMPTY, errno.EEXIST) and isdir(dst):
                        self._resolve_collision(src, dst, folder)
                    else:
                        logging.warning("Failed to rename folder '%s': %s", folder, e)
                except Exception as e:
                    logging.warning("Failed to rename folder '%s': %s", folder, e)
        self.conflicts.end(dry_run=dry_run)

    def _from_nfo(self, folder):
        """`folder` prefixed with the catalogue number its .nfo states, or None."""
        catalogue_number = self.release_info.catalogue_number(join(self.settings.import_folder_path, folder))
        if not catalogue_number:
            return None
        logging.info('Catalogue number of %s taken from its .nfo: %s', folder, catalogue_number)
        return catalogue_number + ' - ' + folder

    def _resolve_collision(self, src, dst, folder):
        """Handle a rename onto a target that already exists.

        Same reasoning as `Mover._move_folder`: a target that is already there means this
        release was imported before, so the source is a duplicate download. The target may
        be a *different* release that merely resolved to the same catalogue number, so the
        two are compared first and anything unequal is left for a human -- warned about
        once, then counted in the cycle's summary line until someone resolves it.

        Even when they compare equal the source is parked rather than deleted:
        `is_same_release` reads track names and lengths, not contents, so "the same
        release" is a strong guess and not a fact.
        """
        # A pair left in place last cycle, with neither folder touched since, would compare
        # the same way again: skip the track reads and the WARNING (bug report 091).
        if self.conflicts.unchanged(src, dst):
            return
        if is_same_release(src, dst):
            self.conflicts.same(src, dst)
            logging.warning('Conflict: %s already exists and holds the same files. Parking %s', dst, src)
            if not Quarantine.put(src, Quarantine.DUPLICATE_RELEASE):
                logging.warning("Could not quarantine '%s'; leaving it in the import folder", folder)
            return
        self.conflicts.differs(src, dst)
