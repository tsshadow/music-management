import glob
from os import listdir
from os.path import isfile, join
import config

# load the libraries that we'll use
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import mutagen.id3
from mutagen.id3 import ID3, TIT2, TIT3, TALB, TPE1, TRCK, TYER

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
        files = [fi for fi in listdir(self.settings.music_folder_path + '/' + folder + '/' + sub_folder) if
                      isfile(join(self.settings.music_folder_path + '/' + folder + '/' + sub_folder, fi))]
        for f in files:
            self.process_file(f)
        splitted_sub_folder = sub_folder.split(' ', 1)
        # Max length is 20, because sometime catid is not filled.
        if (len(splitted_sub_folder[0]) < 20) and (len(splitted_sub_folder) > 1):
            self.db.insert_eps(folder, splitted_sub_folder[0], splitted_sub_folder[1])
        else:
            self.db.insert_eps(folder, 'none', sub_folder)

    def process_file(self, f):
        if f.endswith('.mp3'):
            mp3 = glob.glob(f)
            print(mp3[0])
