import logging
import os
import shutil
from os.path import isdir, isfile, join

from services.common.config_store import ConfigStore as Settings

AUDIO_EXTENSIONS = ('.mp3', '.flac', '.m4a', '.aac', '.wav')
SYNOLOGY_FOLDER = '@eaDir'
MAX_PASSES = 5


def _sub_folders(path) -> list[str]:
    """Directories directly inside path, ignoring Synology's thumbnail folder."""
    return sorted(entry for entry in os.listdir(path) if entry != SYNOLOGY_FOLDER and isdir(join(path, entry)))


def _holds_audio(path) -> bool:
    """True when path itself contains audio; a release folder does, a wrapper does not."""
    return any(entry.lower().endswith(AUDIO_EXTENSIONS) and isfile(join(path, entry)) for entry in os.listdir(path))


def is_wrapper(path) -> bool:
    """
    A wrapper is the extra folder a multipack archive leaves behind: it holds no audio of
    its own, only release folders. A release folder holds its audio directly, so the two
    are told apart without matching on names.

    A single sub folder is ambiguous - it is just as likely to be a "CD1" inside a release -
    so it only counts as a wrapper when that sub folder is itself audio-free, which a disc
    folder never is.
    """
    if _holds_audio(path):
        return False
    folders = _sub_folders(path)
    if not folders:
        return False
    if len(folders) > 1:
        return True
    return not _holds_audio(join(path, folders[0]))


class Flattener:
    """
    Lifts the releases of a multipack out of the folder its archive extracted into.

    A weekly pack unpacks to import/<pack>/<release> while the rest of the pipeline expects
    import/<release>: the Renamer would rename the pack folder and the Mover would fail to
    find a CAT ID in it, leaving every release inside untouched. This step runs between the
    two and puts the releases where they are expected.
    """

    def __init__(self):
        self.settings = Settings()

    def run(self, dry_run=False):
        logging.info('Starting Flatten Step')
        for _ in range(MAX_PASSES):
            try:
                wrappers = [
                    folder
                    for folder in _sub_folders(self.settings.import_folder_path)
                    if is_wrapper(join(self.settings.import_folder_path, folder))
                ]
            except OSError as e:
                logging.error(f'Failed to list folders: {e}')
                return
            if not wrappers:
                break
            logging.info(f'Found {len(wrappers)} multipack folder(s): {wrappers}')
            # Every wrapper is flattened before the pass is judged: `any()` over a generator
            # would short-circuit on the first one that moved and skip the rest.
            moved = [self._flatten(wrapper, dry_run) for wrapper in wrappers]
            if dry_run or not any(moved):
                break
        logging.info('Flatten step completed.')

    def _flatten(self, wrapper, dry_run) -> bool:
        """Move every release out of one wrapper. Returns whether anything actually moved."""
        src_folder = join(self.settings.import_folder_path, wrapper)
        moved = False
        for release in _sub_folders(src_folder):
            src = join(src_folder, release)
            dst = join(self.settings.import_folder_path, release)
            if os.path.exists(dst):
                logging.warning(f'Conflict: {dst} already exists. Leaving {src} in place for manual intervention')
                continue
            if dry_run:
                logging.info(f'Dry run - would move: {src} -> {dst}')
                continue
            try:
                shutil.move(src, dst)
                logging.info(f'Lifted release out of multipack: {src} -> {dst}')
                moved = True
            except (OSError, shutil.Error) as e:
                logging.error(f'Failed to move {src} to {dst}: {e}')
        if not dry_run and moved:
            self._remove_when_empty(wrapper, src_folder)
        return moved

    def _remove_when_empty(self, wrapper, src_folder):
        """
        Drop the wrapper once its releases are out. Anything left behind is pack junk - an
        .nfo, an .sfv, a Synology thumbnail folder - and goes with it. A release that could
        not be moved keeps the wrapper alive so nothing is lost.
        """
        try:
            if _sub_folders(src_folder):
                logging.warning(f'Keeping {src_folder}: it still holds releases that could not be moved')
                return
            shutil.rmtree(src_folder)
            logging.info(f'Removed empty multipack folder: {wrapper}')
        except OSError as e:
            logging.error(f'Failed to remove {src_folder}: {e}')
