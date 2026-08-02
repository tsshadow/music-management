import logging
import os
import re
import shutil
from os import listdir
from os.path import isfile, join

from services.common.config_store import ConfigStore as Settings


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
        only_folders = [f for f in listdir(self.settings.import_folder_path) if not isfile(join(self.settings.import_folder_path, f))]
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
                    os.rename(self.settings.import_folder_path + self.settings.delimiter + folder, self.settings.import_folder_path + self.settings.delimiter + new_name)
                except FileExistsError:
                    src = self.settings.import_folder_path + self.settings.delimiter + folder
                    logging.info('File exists: %s', src)
                    logging.info('Removing file: %s', src)
                    try:
                        shutil.rmtree(src)
                    except Exception as e:
                        logging.info("Thrown exception '%s' while deleting for '%s'", e, folder)
                except Exception as e:
                    error_msg = f"Failed to rename folder '{folder}': {e}"
                    logging.info(error_msg)