import os
from os import listdir
from os.path import isfile, join
import re


def is_parsed(folder):
    if '- ' in folder:
        return True
    else:
        return False


def has_numbers(input_string):
    return any(char.isdigit() for char in input_string)


# Press the green button in the gutter to run the script.
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


def rename(environment):
    if environment == 'docker':
        import_folder_path = "/music/__TODO"
        delimiter = '/'
    else:
        import_folder_path = "\\\\192.0.2.2\\Music\\Eps\\__TODO"
        delimiter = '\\'

    print('starting rename with environment ' + environment)
    only_folders = [f for f in listdir(import_folder_path) if not isfile(join(import_folder_path, f))]

    for folder in only_folders:
        if not is_parsed(folder):
            print('input: ' + folder)
            print('parsed: ' + find_cat_id(folder))
            os.rename(import_folder_path + delimiter + folder, import_folder_path + delimiter + find_cat_id(folder))
        else:
            print('skipped: ' + folder)
# See PyCharm help at https://www.jetbrains.com/help/pycharm/
