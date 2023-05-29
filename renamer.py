import os
import shutil
from os import listdir
from os.path import isfile, join
import re
import config


def has_numbers(input_string):
    return any(char.isdigit() for char in input_string)


def is_parsed(folder):
    if '- ' in folder:
        return True
    else:
        return False


def find_cat_id(folder):
    res = re.findall(r'\(.*?\)', folder)
    res.reverse()
    print(res)
    if len(res) == 0:
        return ' - ' + folder
    else:
        for item in res:
            if has_numbers(item):
                item = item[1:-1]
                return item + ' - ' + folder
    return ' - ' + folder
    pass


class Renamer:

    def __init__(self):
        self.settings = config.Settings()

    def rename(self):
        only_folders = [f for f in listdir(self.settings.import_folder_path) if
                        not isfile(join(self.settings.import_folder_path, f))]

        for folder in only_folders:
            if folder == '@eaDir':
                print('skipping @eaDir')
            elif not is_parsed(folder):
                print('input: ' + folder)
                print('parsed: ' + find_cat_id(folder))
                try:
                    os.rename(self.settings.import_folder_path + self.settings.delimiter + folder,
                              self.settings.import_folder_path + self.settings.delimiter + find_cat_id(folder))
                except FileExistsError:
                    src = self.settings.import_folder_path + self.settings.delimiter + folder
                    print('File exists:' + src)
                    print('Removing file:' + src)
                    try:
                        shutil.rmtree(src)
                    except Exception as e:
                        print('Thrown exception \'' + str(e) + '\' while deleting for \'' + folder + '\'')
                except Exception as e:
                    print('Thrown exception  \'' + str(e) + '\' while moving for \'' + folder + '\'')

        else:
                    print('skipped: ' + folder)
