import logging
import shutil
import string
from os import listdir
from os.path import isfile, join

from data.DatabaseConnector import DatabaseConnector
from data.settings import Settings


def get_cat_id(folder):
    """
    Extract the CAT ID from the folder name and clean it.
    """
    cat_id = folder.split(' ')[0]  # Split at the first space and get the first part

    # Ensure cat_id is not empty before further processing
    if not cat_id:
        return ''

    # Remove specific postfix characters
    if cat_id[-1] in ['B', 'A', 'D', 'E', 'R', 'X', '_']:
        if len(cat_id) > 1 and cat_id[-2].isdigit():  # Ensure there's a digit before the last character
            cat_id = cat_id[:-1]

    # Strip trailing numbers and handle 'PRO' in multiple locations
    cat_id_prefix = cat_id.rstrip(string.digits)
    if 'PRO' in cat_id_prefix:
        cat_id_prefix = cat_id_prefix.replace('PRO', '', 1).rstrip(string.digits)
    if 'PRO' in cat_id_prefix:
        cat_id_prefix = cat_id_prefix.replace('PRO', '', 1).rstrip(string.digits)

    return cat_id_prefix



class Mover:
    def __init__(self):
        self.settings = Settings()
        self.db_connector = DatabaseConnector()

    def get_label(self, key) -> str | None:
        query = f"SELECT 'label' FROM `catid_label` WHERE 'catid' = %s"
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

    def move(self, dry_run=False):
        """
        Move folders to categorized destinations based on their labels.
        """
        logging.info("Starting Move Step")
        only_folders = [f for f in listdir(self.settings.import_folder_path) if
                        not isfile(join(self.settings.import_folder_path, f))]

        for folder in only_folders:
            label = ''
            cat_id = get_cat_id(folder)

            if cat_id:
                # Attempt to match CAT ID with a label
                label = self.get_label(cat_id)
                print(label,cat_id)
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
                    except FileExistsError:
                        logging.warning(f"Conflict: {dst} already exists. Removing {src}")
                        if not dry_run:
                            self.remove(folder)
                    except Exception as e:
                        logging.error(f"Error moving {src} to {dst}: {e}")
            else:
                logging.warning(f"No valid CAT ID found for folder: {folder}")
