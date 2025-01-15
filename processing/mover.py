import logging
import shutil
import string
from os import listdir
from os.path import isfile, join
from data.settings import Settings


def get_cat_id(folder):
    """
    Extract the category ID from the folder name and clean it.
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


def populate_map_from_file(file_path):
    """
    Read a file and populate a dictionary of key-value pairs.
    """
    key_value_map = {}

    try:
        with open(file_path, 'r') as file:
            for line in file:
                # Remove brackets and split key-value pairs
                line = line.strip()[1:-1]
                parts = line.split(':')
                if len(parts) == 2:
                    key = parts[0].strip().strip("'")
                    value = parts[1].strip().strip("'")
                    key_value_map[key] = value
                else:
                    logging.warning(f"Invalid line format in {file_path}: {line}")
    except FileNotFoundError:
        logging.error(f"File not found: {file_path}")
    except Exception as e:
        logging.error(f"Error reading file {file_path}: {e}")

    return key_value_map


class Mover:
    def __init__(self):
        self.settings = Settings()
        file_path = join(self.settings.eps_folder_path, "labels.txt")
        self.labels = populate_map_from_file(file_path)

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
                # Attempt to match category ID with a label
                try:
                    label = self.labels[cat_id]
                except KeyError:
                    logging.warning(f"Category ID {cat_id} not found in labels for folder {folder}")
                    continue

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
                logging.warning(f"No valid category ID found for folder: {folder}")
