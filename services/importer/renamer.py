import errno
import logging
import os
import re
import shutil
from os import listdir
from os.path import isdir, isfile, join

from services.common.config_store import ConfigStore as Settings
from services.importer.release_compare import is_same_release


def has_numbers(input_string):
    return any(char.isdigit() for char in input_string)


def is_parsed(folder):
    return '- ' in folder


def find_cat_id(folder):
    res = re.findall('\\(.*?\\)', folder)
    res.reverse()
    logging.info(res)
    if len(res) == 0:
        return ' - ' + folder
    for item in res:
        if has_numbers(item):
            item = item[1:-1]
            return item + ' - ' + folder
    return ' - ' + folder


class Renamer:
    def __init__(self):
        self.settings = Settings()

    def run(self, dry_run=False):
        logging.info('Starting Rename Step')
        only_folders = [
            f
            for f in listdir(self.settings.import_folder_path)
            if not isfile(join(self.settings.import_folder_path, f))
        ]
        for folder in only_folders:
            if '@eaDir' in folder:
                logging.info('skipping @eaDir')
            elif not is_parsed(folder):
                new_name = find_cat_id(folder)
                logging.info('input: %s', folder)
                logging.info('parsed: %s', new_name)
                if dry_run:
                    logging.info('Dry run - would rename: %s -> %s', folder, new_name)
                    continue
                try:
                    os.rename(
                        self.settings.import_folder_path + self.settings.delimiter + folder,
                        self.settings.import_folder_path + self.settings.delimiter + new_name,
                    )
                except OSError as e:
                    src = self.settings.import_folder_path + self.settings.delimiter + folder
                    dst = self.settings.import_folder_path + self.settings.delimiter + new_name
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

    def _resolve_collision(self, src, dst, folder):
        """Handle a rename onto a target that already exists.

        Same reasoning as `Mover._move_folder`: a target that is already there means this
        release was imported before, so the source is a duplicate download. The mover can
        remove its source on sight because `shutil.move` only conflicts on a completed
        import; here the target may be a *different* release that merely resolved to the
        same catalogue number, so the two are compared first and anything unequal is left
        for a human instead of deleted.
        """
        if is_same_release(src, dst):
            logging.warning('Conflict: %s already exists and holds the same files. Removing %s', dst, src)
            try:
                shutil.rmtree(src)
            except OSError as e:
                logging.warning("Thrown exception '%s' while deleting for '%s'", e, folder)
            return
        logging.warning(
            'Conflict: %s already exists but its contents differ from %s. Leaving both in place for '
            'manual intervention',
            dst,
            src,
        )
