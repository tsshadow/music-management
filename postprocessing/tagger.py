import re
import sys
from os import listdir
from os.path import join, isfile

from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import glob

from data.genressubgenres import genressubgenres
from data.settings import Settings

from data.artistgenre import artist_genre_mapping
from data.publishergenre import publisher_genre_mapping


class Song:
    def __init__(self, path):
        self.settings = Settings()
        self.path = path
        paths = path.rsplit(self.settings.delimiter, 2)
        self.filename = paths[0]
        ep_folder = paths[1]
        self.ep = ep_folder.split('-')[0]
        self.label = paths[2]
        print(self.path, self.label, self.ep)

    def print(self):
        print("genre ", self.genre)
        print("artist ", self.artist)


class Tagger:
    def __init__(self):
        self.rescan = None
        self.settings = Settings()

    def parse_tag(self, name, mp3file):
        parsed_tags = ""
        tags = mp3file.get(name)
        if tags:
            for tag in tags:
                for g in re.split(';|,/', tag):
                    g = g.strip()
                    parsed_tags += g.title() + ";"
            parsed_tags = parsed_tags[:-1]
            mp3file[name] = parsed_tags
        return parsed_tags

    def get_label(self, path):
        label = path.rsplit(self.settings.delimiter, 3)[1]
        return label

    def get_ep(self, path):
        paths = path.rsplit(self.settings.delimiter, 2)
        ep_folder = paths[1]
        return ep_folder.split(' ')[0]

    def get_genre_from_artist(self, mp3file):
        already_exists = False
        artists = self.parse_tag("ARTIST", mp3file)
        for artist in artists:
            for entry in artist_genre_mapping:
                if entry['name'] == artist:
                    for g in re.split(';|,/', self.parse_tag("GENRE", mp3file)):
                        if g == entry['genre']:
                            already_exists = True
                    if not already_exists:
                        mp3file['GENRE'] = self.parse_tag("GENRE", mp3file) + ';' + entry['genre']
                        return mp3file, True
        return mp3file, False
    def get_genre_from_label(self, mp3file):
        already_exists = False
        publisher = self.parse_tag("publisher", mp3file)
        for entry in publisher_genre_mapping:
            if entry['name'] == publisher:
                for g in re.split(';|,/', self.parse_tag("GENRE", mp3file)):
                    if g == entry['genre']:
                        already_exists = True
                if not already_exists:
                    mp3file['GENRE'] = self.parse_tag("GENRE", mp3file) + ';' + entry['genre']
                    print(mp3file['GENRE'])
                    return mp3file, True
        return mp3file, False

    def get_genre_from_subgenres(self, mp3file):
        already_exists = False
        genres = self.parse_tag("GENRE", mp3file)
        for entry in genressubgenres:
            if entry['name'] == genres:
                for g in re.split(';|,/', self.parse_tag("GENRE", mp3file)):
                    if g == entry['genre']:
                        already_exists = True
                if not already_exists:
                    mp3file['GENRE'] = self.parse_tag("GENRE", mp3file) + ';' + entry['genre']
                    print(mp3file['GENRE'])
                    print(mp3file['GENRE'])
                    return mp3file, True
        return mp3file, False

    def get_copyright(self, mp3file):
        pub = self.get_tag(mp3file, 'publisher')
        dat = self.get_tag(mp3file, 'DATE')
        year = str(dat)[0:4]
        if pub:
            if dat:
                cp = pub + " (" + year + ")"
                return cp
            return mp3file.get('publisher')
        return None

    # mp3file.save()
    def tag(self):
        label_folders = [f for f in listdir(self.settings.music_folder_path) if
                         not isfile(join(self.settings.music_folder_path, f))]
        for label in label_folders:
            self.parse_label(label)

    def parse_label(self, label):
        eps_folders = [fi for fi in listdir(self.settings.music_folder_path + self.settings.delimiter + label) if
                       not isfile(join(self.settings.music_folder_path + '\\' + label, fi))]
        for ep in eps_folders:
            if label[0] != '_':
                try:
                    self.parse_ep(label, ep)
                except KeyboardInterrupt:
                    print('KeyboardInterrupt')
                    sys.exit(1)
                except SystemExit:
                    sys.exit(2)
                # except Exception as e:
                # print('Failed to parse ep ' + ep + ' ' + str(e))

    def parse_ep(self, label, ep):
        files = glob.glob(
            self.settings.music_folder_path + self.settings.delimiter + label + self.settings.delimiter + ep + self.settings.delimiter + "*.mp3")
        for song in files:
            try:
                self.parse_song(song)
            except KeyboardInterrupt:
                print('KeyboardInterrupt2')
                sys.exit(1)
            # except Exception as e:
            # print('Failed to parse song ' + song + ' ' + str(e))

    def get_tag(self, mp3file, tag):
        tag = mp3file.get(tag)
        if tag:
            if len(tag) == 1:
                return tag[0]
            return tag
        return tag

    def update_tag(self, mp3file, tag, value):
        tag_value = self.get_tag(mp3file, tag)
        if tag_value != value:
            mp3file[tag] = value
            return mp3file, True
        return mp3file, False

    def parse_song(self, path):
        paths = path.rsplit(self.settings.delimiter, 1)
        filename = paths[1]
        mp3file = MP3(path, ID3=EasyID3)
        EasyID3.RegisterTextKey('publisher', 'TPUB')
        EasyID3.RegisterTXXXKey('parsed', 'parsed')
        if not mp3file.get('parsed') or self.settings.rescan:
            should_update = False

            mp3file, has_changed = self.update_tag(mp3file, "CATALOGNUMBER", self.get_ep(path))
            should_update += has_changed
            if (has_changed):
                print("CATALOGNUMBER changed")
            mp3file, has_changed = self.update_tag(mp3file, "PUBLISHER", self.get_label(path))
            should_update += has_changed
            if (has_changed):
                print("PUBLISHER changed")
            mp3file, has_changed = self.update_tag(mp3file, "GENRE", self.parse_tag("GENRE", mp3file))
            should_update += has_changed
            if (has_changed):
                print("GENRE changed")
            mp3file, has_changed = self.get_genre_from_artist(mp3file)
            should_update += has_changed
            if (has_changed):
                print("get_genre_from_artist changed "+self.parse_tag('Artist', mp3file))
            mp3file, has_changed = self.get_genre_from_label(mp3file)
            should_update += has_changed
            if (has_changed):
                print("get_genre_from_label changed")
            mp3file, has_changed = self.get_genre_from_subgenres(mp3file)
            should_update += has_changed
            if (has_changed):
                print("get_genre_from_subgenres changed")
            if self.get_copyright(mp3file):
                mp3file, has_changed = self.update_tag(mp3file, "COPYRIGHT", self.get_copyright(mp3file))
                should_update += has_changed
                if (has_changed):
                    print("COPYRIGHT changed")
            if should_update:
                mp3file['parsed'] = 'True'
                mp3file.save()
                print('Saved ' + path)
                self.print_mp3(mp3file)
            else:
                print('.', end='')
                # print('Skipped (no changes) ' + path)
                # self.print_mp3(mp3file)

    def print_mp3(self, mp3file):
        print(mp3file["publisher"], mp3file["catalognumber"], mp3file["genre"], mp3file["copyright"],mp3file.get('parsed'))
        pass
