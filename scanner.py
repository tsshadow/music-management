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
        self.allMoods = [];

    def scan(self):
        label_folders = [f for f in listdir(self.settings.music_folder_path) if
                        not isfile(join(self.settings.music_folder_path, f))]
        for label_folder in label_folders:
            if not '__' in label_folder:
                self.process_label_folder(label_folder)

    def process_label_folder(self, label_folder):
        # Insert the label-entry
        self.db.insert_label(label_folder)

        eps_folders = [fi for fi in listdir(self.settings.music_folder_path + '/' + label_folder) if
                       not isfile(join(self.settings.music_folder_path + '/' + label_folder, fi))]

        for ep_folder in eps_folders:
            self.process_ep_folder(label_folder, ep_folder)


    def process_ep_folder(self, label_folder, ep_folder):
        splitted_ep_folder = ep_folder.split(' ', 1)

        # Max length is 20, because sometime catid is not filled.
        if (len(splitted_ep_folder[0]) < 20) and (len(splitted_ep_folder) > 1):
            self.db.insert_eps(label_folder, splitted_ep_folder[0], splitted_ep_folder[1])
        else:
            self.db.insert_eps(label_folder, 'none', ep_folder)

        music_files = [fi for fi in listdir(self.settings.music_folder_path + '/' + label_folder + '/' + ep_folder) if
                       isfile(join(self.settings.music_folder_path + '/' + label_folder + '/' + ep_folder, fi))]

        for file in music_files:
            self.process_file(self.settings.music_folder_path + "/" + label_folder + "/" + ep_folder + "/" + file, label_folder, ep_folder)

    def process_file(self, f, label, ep):
        if f.endswith('.mp3'):
            try:
                mp3 = ID3(f)
                song_mood = str(mp3['TMOO']).split('; ')
                for m in song_mood:
                    self.db.insert_mood(m)
                    self.db.insert_song(f, label, ep)
                    self.db.insert_song_mood(f, m)
            except Exception as e:
                print(e)
