import logging
import os
import re
import shutil
from os import listdir
from os.path import isfile, join
from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.common.config_store import ConfigStore as Settings
from services.tagger.Song.LabelSong import LabelSong
from services.common.Helpers.NotificationService import notification_service

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

    def get_label(self, key) -> str | None:
        query = 'SELECT `label` FROM `rules_catid_label` WHERE `catid` = %s'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
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

    def _move_folder(self, folder, cat_id, dry_run):
        """Processes and moves a single folder based on its CAT ID."""
        label = self.get_label(cat_id)
        if label is None:
            error_msg = f'CAT ID {cat_id} not found in database for folder {folder}. Please add it to rules_catid_label.'
            logging.warning(error_msg)
            return
        src = join(self.settings.import_folder_path, folder)
        dst = join(self.settings.eps_folder_path, label, folder)
        try:
            if not dry_run:
                shutil.move(src, dst)
                logging.info(f'Successfully moved: {src} -> {dst}')
            else:
                logging.info(f'Dry run - would move: {src} -> {dst}')
            try:
                post_processing_songs(dst)
            except Exception as e:
                logging.error(f'Post-processing failed for {dst}: {e}')
        except FileExistsError:
            logging.warning(f'Conflict: {dst} already exists. Removing {src}')
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
        only_folders = [f for f in listdir(self.settings.import_folder_path) if not isfile(join(self.settings.import_folder_path, f))]
        for folder in only_folders:
            cat_id = get_cat_id(folder)
            if cat_id:
                self._move_folder(folder, cat_id, dry_run)
            else:
                error_msg = f'No valid CAT ID found for folder: {folder}. Manual intervention required.'
                logging.warning(error_msg)