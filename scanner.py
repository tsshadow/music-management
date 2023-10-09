import multiprocessing
from multiprocessing.pool import ThreadPool
from os import listdir
from os.path import isfile, join
from threading import Thread

from mutagen.id3 import ID3

import config
from os import listdir
from os.path import isfile, join

import config


# load the libraries that we'll use

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
        print(folder)
        sub_folder = [fi for fi in listdir(self.settings.music_folder_path + '/' + folder) if
                      not isfile(join(self.settings.music_folder_path + '/' + folder, fi))]
        mood_label = []
        for f in sub_folder:
            self.process_folder_contents(folder, f, mood_label)
        self.db.insert_label(folder, str(len(sub_folder)), ','.join(mood_label))

    def process_folder_contents(self, folder, sub_folder, mood_label):
        files = [fi for fi in listdir(self.settings.music_folder_path + '/' + folder + '/' + sub_folder) if
                 isfile(join(self.settings.music_folder_path + '/' + folder + '/' + sub_folder, fi))]
        mood_eps = []
        for f in files:
            self.process_file(self.settings.music_folder_path + "/" + folder + "/" + sub_folder + "/" + f, mood_eps)
        splitted_sub_folder = sub_folder.split(' ', 1)

        for m in mood_eps:
            if not m in mood_label:
                mood_label.append(m)

        # Max length is 20, because sometime catid is not filled.
        if (len(splitted_sub_folder[0]) < 20) and (len(splitted_sub_folder) > 1):
            self.db.insert_eps(folder, splitted_sub_folder[0], splitted_sub_folder[1], ';'.join(mood_eps))
        else:
            self.db.insert_eps(folder, 'none', sub_folder, ';'.join(mood_eps))

    def process_file(self, f, mood_eps):
        if f.endswith('.mp3'):
            try:
                mp3 = ID3(f)
                song_mood = str(mp3['TMOO']).split('; ')
                for m in song_mood:
                    if not m in mood_eps:
                        mood_eps.append(m)
            except Exception as e:
                print(e)
