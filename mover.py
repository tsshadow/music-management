import os
import string
from os import listdir
from os.path import isfile, join
from labels import labels
import config


def get_cat_id(folder):
    cat_id = folder.split(' ')
    return cat_id[0]


def get_label_by_cat_id():
    print('a')


class Mover:

    def __init__(self):
        self.settings = config.Settings()

    def move(self):
        only_folders = [f for f in listdir(self.settings.import_folder_path) if
                        not isfile(join(self.settings.import_folder_path, f))]
        for folder in only_folders:
            label = ''
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

                if cat_id_prefix == '':
                    print('No label found for ' + folder)
                else:
                    # Find label
                    try:
                        label = labels[cat_id_prefix]
                    except Exception as e:
                        print(str(e) + ' not found in label list')
                    else:
                        # copy file
                        try:
                            src = self.settings.import_folder_path + self.settings.delimiter + folder
                            dst = self.settings.music_folder_path + self.settings.delimiter + label + self.settings.delimiter + folder
                            print('src: ' + src)
                            print('dst: ' + dst)
                            os.rename(src, dst)
                        except Exception as e:
                            print('Thrown exception  \'' + str(e) + '\' for \'' + folder + '\'')


