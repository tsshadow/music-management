import os
import re
import sys

from typing import Final
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import glob

from data.genressubgenres import genressubgenres
from data.settings import Settings

from data.artistgenre import artist_genre_mapping
from data.publishergenre import publisher_genre_mapping

import librosa

s = Settings()

# MP# Tags in use
# noinspection SpellCheckingInspection
CATALOG_NUMBER: Final = "CATALOGNUMBER"
PUBLISHER: Final = "PUBLISHER"
DATE: Final = "DATE"
BPM: Final = "BPM"
COPYRIGHT: Final = "COPYRIGHT"
GENRE: Final = "GENRE"
ARTIST: Final = "ARTIST"
PARSED: Final = "PARSED"

EasyID3.RegisterTextKey('publisher', 'TPUB')
EasyID3.RegisterTXXXKey('parsed', 'parsed')


def to_semicolon_separated_tag(tags, format_tag="None"):
    if len(tags) == 1:
        return tags[0]
    if len(tags) > 1:
        parsed_tags = ""
        for tag in tags:
            for g in re.split(';|,/', tag):
                g = g.strip()
                if format_tag == "None":
                    parsed_tags += g + ";"
                elif format_tag == "Title":
                    parsed_tags += g.title() + ";"

                parsed_tags = parsed_tags[:-1]
        return parsed_tags


class Song:
    def __init__(self, path):
        # Setup member variables
        self.has_changes = False
        paths = path.rsplit(s.delimiter, 2)
        self._path = path
        self._filename = str(paths[-1])
        self._extension = os.path.splitext(self._filename)[1]
        self._publisher = None  # no default
        self._catalog_number = None  # no default
        self.mp3file = MP3(path, ID3=EasyID3)

    def parse(self):
        if not self.has_changes or s.rescan:
            self.analyze_track()
            self.update_tags()

    def check_or_update_tag(self, tag, value):
        tag_value = self.get_tag_as_string(tag)
        if tag_value is None or tag_value != value:
            if tag_value is not None and value is not None and tag_value.title() == value.title():
                self.mp3file[tag] = value + "_CapError"
                self.has_changes = True
                if s.debug:
                    print("cap error for ", tag)
                self.save_file()
            self.mp3file[tag] = value
            if s.debug:
                print("updated ", tag, "to", value)
            self.has_changes = True

    def calculate_copyright(self):
        pub = self.publisher()
        dat = self.date()
        year = str(dat)[0:4]
        if pub:
            if dat:
                cp = pub + " (" + year + ")"
                return cp
            return self.publisher()
        return None

    def update_tags(self):
        self.check_or_update_tag(PUBLISHER, self._publisher)
        self.check_or_update_tag(CATALOG_NUMBER, self._catalog_number)
        self.check_or_update_tag(GENRE, self.genre())  # should reformat
        self.check_or_update_tag(ARTIST, self.artist())  # should reformat
        self.check_or_update_tag(COPYRIGHT, self.calculate_copyright())
        self.save_file()

    def save_file(self):
        if self.has_changes and not s.dryrun:
            self.mp3file.save()

    def get_tag(self, tag):
        return self.mp3file.get(tag)

    def get_tag_as_string(self, tag):
        value = self.mp3file.get(tag)
        if value is None:
            return ""
        else:
            return to_semicolon_separated_tag(value)

    def set_tag(self, tag, value):
        self.mp3file[tag] = value

    def print(self):
        if s.debug:
            print("path           ", self.path())
            print("filename       ", self.filename())
            print("extension      ", self.extension())
            print("genre          ", self.genre())
            print("artist         ", self.artist())
            print("copyright      ", self.copyright())
            print("publisher      ", self.publisher(), )
            print("publisher2     ", self._publisher)
            print("catalog_number ", self.catalog_number())
            print("catalog_number2", self._catalog_number)
            print("bpm            ", self.bpm())
            print("\n\n")

    def analyze_track(self):
        if not self.bpm():
            try:
                audio_file = librosa.load(self._path)
                y, sr = audio_file
                tempo = librosa.beat.beat_track(y=y, sr=sr)
                # noinspection PyTypeChecker
                self.set_tag(BPM, str(round(tempo[0][0])))
            except Exception as e:
                print('Failed to parse bpm for ' + self._filename + str(e))
                return 0

    # Getter wrappers
    def genre(self):
        return self.get_tag_as_string(GENRE)

    def bpm(self):
        return self.get_tag_as_string(BPM)

    def artist(self):
        return self.get_tag_as_string(ARTIST)

    def copyright(self):
        return self.get_tag_as_string(COPYRIGHT)

    def publisher(self):
        return self.get_tag_as_string(PUBLISHER)

    def catalog_number(self):
        return self.get_tag_as_string(CATALOG_NUMBER)

    def filename(self):
        return self._filename

    def path(self):
        return self._path

    def extension(self):
        return self._extension

    def parsed(self):
        return self.get_tag_as_string(PARSED)

    def date(self):
        return self.get_tag_as_string(DATE)


class LabelSong(Song):
    def __init__(self, path):
        super().__init__(path)
        paths = path.rsplit(s.delimiter, 2)
        self._publisher = str(paths[0].split(s.delimiter)[-1])
        self._catalog_number = str(paths[1].split(' ')[0])
        self.parse()


class YoutubeSong(Song):
    def __init__(self, path):
        super().__init__(path)
        self._publisher = "Youtube"
        self._catalog_number = None

        self.parse()


class SoundcloudSong(Song):
    def __init__(self, path):
        super().__init__(path)
        self._publisher = "Soundcloud"
        self._catalog_number = None

        self.parse()


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
        publisher = self.get_tag(mp3file, "publisher")
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
        label_folders = [f for f in os.listdir(self.settings.eps_folder_path) if
                         not os.path.isfile(os.path.join(self.settings.eps_folder_path, f))]
        for label in label_folders:
            self.parse_label(label)

    # sc_folder = self.settings.music_folder_path + self.settings.delimiter + "Soundcloud"
    # sound_cloud_folders = [f for f in os.listdir(sc_folder) if
    #                        not os.path.isfile(os.path.join(sc_folder, f))]
    # for sound_cloud in sound_cloud_folders:
    #     self.parse_folder("Soundcloud" + self.settings.delimiter + sound_cloud)
    #
    # yt_folder = self.settings.music_folder_path + self.settings.delimiter + "Youtube"
    # sound_cloud_folders = [f for f in os.listdir(yt_folder) if
    #                        not os.path.isfile(os.path.join(yt_folder, f))]
    # for sound_cloud in sound_cloud_folders:
    #     self.parse_label(sound_cloud)

    def parse_label(self, label):
        eps_folders = [fi for fi in os.listdir(self.settings.eps_folder_path + self.settings.delimiter + label) if
                       not os.path.isfile(os.path.join(self.settings.eps_folder_path + '\\' + label, fi))]
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
                #     print('Failed to parse ep ' + ep + ' ' + str(e))

    def parse_folder(self, folder):
        path = self.settings.music_folder_path + self.settings.delimiter + folder
        folders = [fi for fi in os.listdir(path) if
                   not os.path.isfile(os.path.join(path, fi))]
        files = [fi for fi in os.listdir(path) if
                 os.path.isfile(os.path.join(path, fi))]

        for file in files:
            self.parse_song(
                self.settings.music_folder_path + self.settings.delimiter + folder + self.settings.delimiter + file)
        for sub_folder in folders:
            if sub_folder[0] != '_':
                try:
                    self.parse_folder(folder + self.settings.delimiter + sub_folder)
                except KeyboardInterrupt:
                    print('KeyboardInterrupt')
                    sys.exit(1)
                except SystemExit:
                    sys.exit(2)
                # except Exception as e:
                #     print('Failed to parse sub_folder ' + sub_folder + ' ' + str(e))

    def parse_ep(self, label, ep):
        files = glob.glob(
            self.settings.eps_folder_path + self.settings.delimiter + label + self.settings.delimiter + ep + self.settings.delimiter + "*.mp3")
        for song in files:
            try:
                self.parse_song(song)
            except KeyboardInterrupt:
                print('KeyboardInterrupt')
                sys.exit(1)
            # except Exception as e:
            #     print('Failed to parse song ' + song + ' ' + str(e))

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
            if tag_value and value and tag_value.title() == value.title():
                print('Capitalization error for ' + tag_value + ' ' + value)
                mp3file[tag] = value + "_CapError"
                return mp3file, 2
            mp3file[tag] = value
            return mp3file, 1
        return mp3file, 0

    def parse_song(self, path):
        song = LabelSong(path)
        # song.print()
        #
        #         # GENRE
        #         genre = self.parse_tag("GENRE", mp3file)
        #         if genre:
        #             mp3file, has_changed = self.update_tag(mp3file, "GENRE", genre)
        #             should_update += has_changed
        #             if has_changed:
        #                 print("Genre changed " + genre)
        #
        #         mp3file, has_changed = self.get_genre_from_artist(mp3file)
        #         should_update += has_changed
        #         if has_changed:
        #             print("get_genre_from_artist changed " + self.parse_tag('Artist', mp3file))
        #         # mp3file, has_changed = self.get_genre_from_label(mp3file)
        #         # should_update += has_changed
        #         # if has_changed:
        #         #     print("get_genre_from_label changed ")
        #         mp3file, has_changed = self.get_genre_from_subgenres(mp3file)
        #         should_update += has_changed
        #         if has_changed:
        #             print("get_genre_from_subgenres changed ")
        #         if self.get_copyright(mp3file):
        #             mp3file, has_changed = self.update_tag(mp3file, "COPYRIGHT", self.parse_tag('COPYRIGHT', mp3file))
        #             should_update += has_changed
        #             if has_changed:
        #                 print("COPYRIGHT changed " + self.parse_tag('COPYRIGHT', mp3file))
        #         if should_update:
        #             mp3file['parsed'] = 'True'
        #             mp3file.save()
        #             print('Saved ' + filename)
        #             self.print_mp3(mp3file)
        #         # else:
        #         #     print('.', end='')
        #         # print('Skipped (no changes) ' + path)
        #         # self.print_mp3(mp3file)

    def print_mp3(self, mp3file):
        print(mp3file["publisher"], mp3file["catalognumber"], mp3file["genre"], mp3file["bpm"], mp3file["copyright"],
              mp3file.get('parsed'))
        pass

    def analyze_bpm(self, path):
        try:
            audio_file = librosa.load(path)
            y, sr = audio_file
            tempo = librosa.beat.beat_track(y=y, sr=sr)
            return str(round(tempo[0][0]))
        except Exception as e:
            print('Failed to parse bpm for ' + path + str(e))
            return 0
