import logging
import os
import re
import shutil
from os import listdir
from os.path import isfile, join

from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.Helpers.LmsScanTrigger import lms_scan_trigger
from services.common.Helpers.NotificationService import notification_service
from services.importer.label_proposal_store import LabelProposalStore
from services.importer.label_resolver import resolve
from services.importer.release_compare import is_same_release
from services.tagger.Song.LabelSong import LabelSong


def get_cat_id(folder: str):
    """
    Extracts the catalog ID (CAT ID) from a folder name.
    - Takes the first space-separated part.
    - Keeps letters/numbers up to but not including at least 3 consecutive numbers.
    """
    if ' ' in folder:
        first_part = folder.split(' ')[0]
        if '247HC' in first_part:
            return '247HC'
        if 'R909' in first_part:
            return 'R909'
        if 'UNFD' in first_part:
            return 'UNFD'
        first_part = first_part.replace('_', '').replace('-', '')
        match = re.match('^([A-Za-z]*\\d*[A-Za-z]*)(?=\\d{3,})', first_part)
        if match:
            return match.group(1)
        return first_part
    return None


def post_processing_songs(folder_path):
    """
    Call LabelSong(path) for every supported audio file in the folder,
    excluding Synology's @eaDir directories and non-files.
    """
    supported_exts = ('.mp3', '.flac', '.m4a', '.aac', '.wav')
    for root, dirs, files in os.walk(folder_path):
        dirs[:] = [d for d in dirs if d != '@eaDir']
        for file in files:
            if file.lower().endswith(supported_exts):
                full_path = os.path.join(root, file)
                if not os.path.isfile(full_path):
                    logging.warning(f'Skipping non-file: {full_path}')
                    continue
                try:
                    logging.info(f'Processing file with LabelSong: {full_path}')
                    s = LabelSong(str(full_path))
                    s.parse()
                    notification_service.notify(str(s), title='Import Complete')
                except Exception as e:
                    logging.error(f'Failed to process {full_path} with LabelSong: {e}')


class Mover:
    def __init__(self):
        self.settings = Settings()
        self.db_connector = DatabaseConnector()
        self.proposals = LabelProposalStore()

    def _propose(self, folder, cat_id):
        """
        Record a release this step could not place, so it can be reviewed once instead
        of re-warned on every cycle for as long as it sits in the import folder.
        """
        src = join(self.settings.import_folder_path, folder)
        import_folder_name = os.path.basename(self.settings.import_folder_path.rstrip(os.sep))
        self.proposals.record(
            folder, resolve(src, import_folder_name=import_folder_name, catid_from_name=cat_id or None)
        )

    def get_label(self, key) -> str | None:
        query = 'SELECT `label` FROM `rules_catid_label` WHERE `catid` = %s'
        try:
            with self.db_connector.connection() as connection, connection.cursor() as cursor:
                cursor.execute(query, key)
                result = cursor.fetchone()
                if result:
                    return str(result[0])
                return None
        except Exception as e:
            logging.error(f'Error querying database: {e}')
            return None

    def remove(self, folder):
        """
        Remove a folder.
        """
        src = join(self.settings.import_folder_path, folder)
        logging.info(f'Removing folder: {src}')
        try:
            shutil.rmtree(src)
        except Exception as e:
            logging.error(f'Error removing {src}: {e}')

    def _resolve_conflict(self, folder, src, dst, dry_run):
        """Decides what to do when the label folder already holds this release.

        Same rule as the renamer: identical file names and sizes mean the release was
        imported before and this is a duplicate download, so the source goes. Anything
        else may be a different release that resolved to the same folder name, and gets
        left alone rather than merged into the one already there.
        """
        if not is_same_release(src, dst):
            logging.warning(
                'Conflict: %s already exists but its contents differ from %s. '
                'Leaving both in place for manual intervention',
                dst,
                src,
            )
            return
        logging.warning('Conflict: %s already exists and holds the same files. Removing %s', dst, src)
        if not dry_run:
            self.remove(folder)

    def _move_folder(self, folder, cat_id, dry_run):
        """Processes and moves a single folder based on its CAT ID."""
        label = self.get_label(cat_id)
        if label is None:
            error_msg = (
                f'CAT ID {cat_id} not found in database for folder {folder}. Please add it to rules_catid_label.'
            )
            logging.warning(error_msg)
            self._propose(folder, cat_id)
            return
        src = join(self.settings.import_folder_path, folder)
        dst = join(self.settings.eps_folder_path, label, folder)
        # Checked before the move, not after it, because shutil.move does not fail on an
        # existing destination directory -- it moves *into* it, so a second copy of a
        # release ends up at dst/<same name>/, one level deeper, and stays there. The
        # exception branch below only fires on the third copy, once that nested folder
        # exists too. 429 release folders on production contained themselves this way.
        if os.path.exists(dst):
            self._resolve_conflict(folder, src, dst, dry_run)
            return
        try:
            if not dry_run:
                shutil.move(src, dst)
                logging.info(f'Successfully moved: {src} -> {dst}')
                # Both paths: the new one so LMS reads the files, the old one so the rows
                # underneath a folder that is now gone get removed.
                lms_scan_trigger.notify([src, dst])
            else:
                logging.info(f'Dry run - would move: {src} -> {dst}')
            try:
                post_processing_songs(dst)
            except Exception as e:
                logging.error(f'Post-processing failed for {dst}: {e}')
        except (FileExistsError, shutil.Error) as e:
            # shutil.move(src, dst) treats an existing "dst" directory as a target to move
            # INTO (i.e. src ends up at dst/basename(src)), not as an in-place conflict. If
            # that folder (from a previous successful import of the same release) already
            # exists too, shutil.move raises shutil.Error (a subclass of OSError on modern
            # Python, so it used to be silently swallowed by the generic "except OSError"
            # branch below as a bogus "check disk space/filesystem" error) instead of
            # FileExistsError. Either way this means the release was already imported
            # previously, so the conflicting leftover source folder is a genuine duplicate:
            # treat both exceptions identically and remove the source so it stops being
            # retried (and logged as an error) on every single import cycle forever.
            logging.warning(f'Conflict: {dst} already exists ({e}). Removing {src}')
            if not dry_run:
                self.remove(folder)
        except PermissionError as e:
            logging.error(f'Permission denied when moving {src} to {dst}: {e}')
        except OSError as e:
            logging.error(f'OS error when moving {src} to {dst} (check disk space/filesystem): {e}')
        except Exception as e:
            logging.error(f'Unexpected error moving {src} to {dst}: {e}')

    def run(self, dry_run=False):
        """
        Move folders to categorized destinations based on their library_labels.
        """
        logging.info('Starting Move Step')
        only_folders = [
            f
            for f in listdir(self.settings.import_folder_path)
            if not isfile(join(self.settings.import_folder_path, f))
        ]
        for folder in only_folders:
            cat_id = get_cat_id(folder)
            if cat_id:
                self._move_folder(folder, cat_id, dry_run)
            else:
                error_msg = f'No valid CAT ID found for folder: {folder}. Manual intervention required.'
                logging.warning(error_msg)
                self._propose(folder, None)
