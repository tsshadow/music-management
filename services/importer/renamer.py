import logging
import os
import shutil
from os import listdir
from os.path import isfile, join
import re

from services.common.settings import Settings
from services.common.Helpers.NotificationService import notification_service


def has_numbers(input_string):
    return any((char.isdigit() for char in input_string))

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

    def run(self):
        logging.info('Starting Rename Step')
        only_folders = [f for f in listdir(self.settings.import_folder_path) if not isfile(join(self.settings.import_folder_path, f))]
        for folder in only_folders:
            if '@eaDir' in folder:
                logging.info('skipping @eaDir')
            elif not is_parsed(folder):
                logging.info('input: %s', folder)
                logging.info('parsed: %s', find_cat_id(folder))
                try:
                    os.rename(self.settings.import_folder_path + self.settings.delimiter + folder, self.settings.import_folder_path + self.settings.delimiter + find_cat_id(folder))
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
                    notification_service.notify(error_msg, title="Import Error")
