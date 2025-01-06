import shutil
import string
from os import listdir
from os.path import isfile, join
from data.settings import Settings
from postprocessing.Song.LabelSong import LabelSong


def get_cat_id(folder):
    cat_id = folder.split(' ')
    return cat_id[0]


def populate_map_from_file(file_path):
    # Initialize an empty dictionary
    key_value_map = {}

    # Read the content of the file
    with open(file_path, 'r') as file:
        for line in file:
            # Remove leading/trailing whitespace and square brackets
            line = line.strip()[1:-1]

            # Split the line at the colon
            parts = line.split(':')

            # Ensure there are exactly two parts (key and value)
            if len(parts) == 2:
                key = parts[0].strip().strip("'")  # Remove extra whitespace and single quotes
                value = parts[1].strip().strip("'")  # Remove extra whitespace and single quotes
                key_value_map[key] = value
            else:
                print(f"Error: Line '{line}' in '{file_path}' is not in key:value format. Skipping...")
    return key_value_map


class Mover:

    def __init__(self):
        self.settings = Settings()
        file_path = self.settings.eps_folder_path + self.settings.delimiter + "labels.txt"  # Path to your text file
        print(file_path)
        self.labels = populate_map_from_file(file_path)

    def remove(self, folder):
        src = self.settings.import_folder_path + self.settings.delimiter + folder
        print('File exists:' + src)
        print('Removing file:' + src)
        try:
            shutil.rmtree(src)
        except Exception as e:
            print('Thrown exception (type: ' + e.__class__.__name__ + ') \'' + str(
                e) + '\' while deleting for \'' + folder + '\'')

    def move(self):
        print("Starting Move Step")
        only_folders = [f for f in listdir(self.settings.import_folder_path) if
                        not isfile(join(self.settings.import_folder_path, f))]
        for folder in only_folders:
            label = ''
            cat_id = get_cat_id(folder)

            if len(cat_id):
                last_char = cat_id[-1]

                # Remove E, D, R, or B postfix
                if last_char == 'B' or last_char == 'A' or last_char == 'D' or last_char == 'E' or last_char == 'R' or last_char == 'X' or last_char == '_':
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
                        label = self.labels[cat_id_prefix]
                    except Exception as e:
                        print(str(e) + ' not found in label list')
                    else:
                        # copy file
                        try:
                            src = self.settings.import_folder_path + self.settings.delimiter + folder
                            dst = self.settings.eps_folder_path + self.settings.delimiter + label + self.settings.delimiter + folder
                            print('src: ' + src)
                            print('dst: ' + dst)
                            shutil.move(src, dst)
                            # Done moving:

                        except FileExistsError:
                            self.remove(folder)
                        except Exception as e:
                            if 'already exists' in str(e):
                                self.remove(folder)
                            else:
                                print('Thrown exception (type: ' + e.__class__.__name__ + ') \'' + str(
                                    e) + '\' while moving for \'' + folder + '\'')

