import os
from os import listdir
from os.path import isfile, join
import string

from labels import labels


def get_cat_id(folder):
    cat_id = folder.split(' ')
    return cat_id[0]


def get_label_by_cat_id():
    print('a')


def move(environment):
    if environment == 'docker':
        import_folder_path = "/music/__TODO"
        music_folder_path = "/music"
        delimiter = '/'
    else:
        import_folder_path = "\\\\192.0.2.2\\Music\\Eps\\__TODO"
        music_folder_path = "\\\\192.0.2.2\\Music\\Eps"
        delimiter = '\\'

    print('starting move with environment ' + environment)
    only_folders = [f for f in listdir(import_folder_path) if not isfile(join(import_folder_path, f))]
    for folder in only_folders:
        cat_id = get_cat_id(folder)

        if len(cat_id):
            last_char = cat_id[-1]

            # Remove E, D, R, or B postfix
            if last_char == 'B' or last_char == 'D' or last_char == 'E' or last_char == 'R':
                if cat_id[-2].isdigit():
                    cat_id = cat_id[:-1]

            # Strip last numbers after PRO
            cat_id_prefix = cat_id.rstrip(string.digits)

            # remove pro if used
            if 'PRO' in cat_id_prefix:
                cat_id_prefix = cat_id_prefix[:-3]
            # remove pro if used
            if 'PRO' in cat_id_prefix:
                cat_id_prefix = cat_id_prefix[:-3]

            # Remove last numbers before PRO
            cat_id_prefix = cat_id_prefix.rstrip(string.digits)
        try:
            label = labels[cat_id_prefix]
            src = import_folder_path + delimiter + folder
            dst = music_folder_path + delimiter + label + delimiter + folder
            print('src: ' + src)
            print('dst: ' + dst)
            os.rename(src, dst)
        except Exception as e:
            print(e)
            print('Thrown exception  \'' + str(e) + '\' for \'' + folder + '\'')
