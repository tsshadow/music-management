# This is a sample Python script.
import os
# Press Shift+F10 to execute it or replace it with your code.
# Press Double Shift to search everywhere for classes, files, tool windows, actions, and settings.
from os import listdir
from os.path import isfile, join
import re

import eps_scanner

# musicFolderPath = "\\\\192.0.2.2\\Music\\Eps\\__TODO"
musicFolderPath = "/todo"


def is_parsed(folder):
    if '- ' in folder:
        return True
    else:
        return False


def has_numbers(inputString):
    return any(char.isdigit() for char in inputString)


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


def rename():
    onlyfolders = [f for f in listdir(musicFolderPath) if not isfile(join(musicFolderPath, f))]

    for folder in onlyfolders:

        if not is_parsed(folder):
            print('input: ' + folder)
            print('parsed: ' + find_cat_id(folder))
            os.rename(musicFolderPath+'/'+folder, musicFolderPath+'/'+find_cat_id(folder))
        else:
            print('skipped: ' + folder)
# See PyCharm help at https://www.jetbrains.com/help/pycharm/

