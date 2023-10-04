from os import listdir
from os.path import isfile, join
import config


class Scanner:

    def __init__(self, db):
        self.settings = config.Settings()
        self.db = db

    def scan(self):
        self.db.clear_eps()
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
        for f in sub_folder:
            self.process_folder_contents(folder, f)
        self.db.insert_label(folder, str(len(sub_folder)))

    def process_folder_contents(self, folder, sub_folder):
        catid = sub_folder.split(' ')[0];
        # Max length is 20, because sometime catid is not filled.
        if len(catid) < 20:
            self.db.insert_eps(folder, sub_folder.split(' ')[0])
