import logging
import os
import re
import shutil

from os import listdir
from os.path import isfile, join

from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector
from data.settings import Settings
from postprocessing.Song.LabelSong import LabelSong

def get_cat_id(folder: str):
    """
    Extracts the catalog ID (CAT ID) from a folder name.
    - Takes the first space-separated part.
    - Keeps letters/numbers up to but not including at least 3 consecutive numbers.
    """
    if ' ' in folder:
        first_part = folder.split(' ')[0]  # Extract first space-separated segment

        # Exceptions, because it has 3 characters in its name.
        if '247HC' in first_part:
            return '247HC'
        if 'R909' in first_part:
            return 'R909'
        if 'UNFD' in first_part:
            return 'UNFD'

        # Remove underscores and dashes (common formatting artifacts)
        first_part = first_part.replace('_', '').replace('-', '')

        # Match letters/numbers before at least 3 consecutive digits
        match = re.match(r"^([A-Za-z]*\d*[A-Za-z]*)(?=\d{3,})", first_part)

        if match:
            return match.group(1)  # Return only the first matched section

        return first_part  # Fallback return if no match is found
    else:
        return None


def post_processing_songs(folder_path):
    """
    Call LabelSong(path) for every supported audio file in the folder,
    excluding Synology's @eaDir directories and non-files.
    """
    supported_exts = (".mp3", ".flac", ".m4a", ".aac", ".wav")
    for root, dirs, files in os.walk(folder_path):
        # Exclude Synology metadata directories
        dirs[:] = [d for d in dirs if d != "@eaDir"]
        for file in files:
            if file.lower().endswith(supported_exts):
                full_path = os.path.join(root, file)
                if not os.path.isfile(full_path):
                    logging.warning(f"Skipping non-file: {full_path}")
                    continue
                try:
                    logging.info(f"Processing file with LabelSong: {full_path}")
                    s = LabelSong(str(full_path))
                    s.parse()
                except Exception as e:
                    logging.error(f"Failed to process {full_path} with LabelSong: {e}")


class Mover:
    def __init__(self):
        self.settings = Settings()
        self.db_connector = DatabaseConnector()

    def get_label(self, key) -> str | None:
        query = f"SELECT `label` FROM `catid_label` WHERE `catid` = %s"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, key)
                result = cursor.fetchone()
                if result:
                    return str(result[0])
                else:
                    return None
        except Exception as e:
            logging.error(f"Error querying database: {e}")
            return None

    def remove(self, folder):
        """
        Remove a folder.
        """
        src = join(self.settings.import_folder_path, folder)
        logging.info(f"Removing folder: {src}")
        try:
            shutil.rmtree(src)
        except Exception as e:
            logging.error(f"Error removing {src}: {e}")

    def run(self, dry_run=False):
        """
        Move folders to categorized destinations based on their labels.
        """
        logging.info("Starting Move Step")
        only_folders = [f for f in listdir(self.settings.import_folder_path) if
                        not isfile(join(self.settings.import_folder_path, f))]

        for folder in only_folders:
            cat_id = get_cat_id(folder)

            if cat_id:
                # Attempt to match CAT ID with a label
                label = self.get_label(cat_id)
                if label is None:
                    logging.warning(f"CAT ID {cat_id} not found in labels for folder {folder}")
                else:
                    # Build source and destination paths
                    src = join(self.settings.import_folder_path, folder)
                    dst = join(self.settings.eps_folder_path, label, folder)

                    # Move or simulate move
                    try:
                        if not dry_run:
                            shutil.move(src, dst)
                        logging.info(f"Moved: {src} -> {dst}")
                        post_processing_songs(dst)
                    except FileExistsError:
                        logging.warning(f"Conflict: {dst} already exists. Removing {src}")
                        if not dry_run:
                            self.remove(folder)
                    except Exception as e:
                        logging.error(f"Error moving {src} to {dst}: {e}")
            else:
                logging.warning(f"No valid CAT ID found for folder: {folder}")
