from os import listdir
from os.path import isfile, join
import config




class Scanner:

    def __init__(self, db):
        self.settings = config.Settings()
        self.db = db

    def scan(self):
        total_count = 0
        only_folders = [f for f in listdir(self.settings.music_folder_path) if
                        not isfile(join(self.settings.music_folder_path, f))]
        for folder in only_folders:
            if not '__' in folder:
                self.process_folder(folder)

    def process_folder(self, folder):
        sub_folder = [fi for fi in listdir(self.settings.music_folder_path + '/' + folder) if
                      not isfile(join(self.settings.music_folder_path + '/' + folder, fi))]
        print(folder + ', ' + str(len(sub_folder)))
        self.process_folder_contents(sub_folder)
        self.db.insert_label(folder, str(len(sub_folder)))

    def process_folder_contents(self, sub_folder):
        pass