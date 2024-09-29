import re
import os
import sys

from typing import Final

from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.easyid3 import EasyID3
import glob

from mutagen.wave import WAVE

from data.genressubgenres import genressubgenres
from data.settings import Settings

from data.artistgenre import artist_genre_mapping
from data.publishergenre import publisher_genre_mapping
from enum import Enum

import librosa

s = Settings()

ARTIST_REGEX: Final = "\s(&|feat\.?|featuring|features|ft\.?|presenting|X|pres\.?|versus|vs\.?)\s"


class FORMAT(Enum):
    NONE = 0
    RECAPITALIZE = 1


# MP# Tags in use
# noinspection SpellCheckingInspection
CATALOG_NUMBER: Final = "CATALOGNUMBER"
PUBLISHER: Final = "PUBLISHER"
PUBLISHER_OLD: Final = "PUBLISHER_OLD"
DATE: Final = "DATE"
BPM: Final = "BPM"
COPYRIGHT: Final = "COPYRIGHT"
GENRE: Final = "GENRE"
ARTIST: Final = "ARTIST"
ALBUM_ARTIST: Final = "ALBUM_ARTIST"
PARSED: Final = "PARSED"

EasyID3.RegisterTextKey('publisher_old', 'TPUB')
EasyID3.RegisterTXXXKey('publisher', 'publisher')
EasyID3.RegisterTXXXKey('parsed', 'parsed')


def to_semicolon_separated_tag(tags, format_tag=FORMAT.NONE):
    if len(tags) == 1:
        if format_tag == FORMAT.NONE:
            return tags[0]
        elif format_tag == FORMAT.RECAPITALIZE:
            return tags[0].title()
    if len(tags) > 1:
        parsed_tags = ""
        for tag in tags:
            for g in re.split(';|,/', tag):
                g = g.strip()
                if format_tag == FORMAT.NONE:
                    parsed_tags += g + ";"
                elif format_tag == FORMAT.RECAPITALIZE:
                    parsed_tags += g.title() + ";"
                parsed_tags = parsed_tags[:-1]
        return parsed_tags


def parse_artist(artist):
    parsed = re.sub(ARTIST_REGEX, ";", artist)
    return parsed


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

        if self._extension.lower() == ".flac":
            self.mp3file = FLAC(path)
        if self._extension.lower() == ".mp3":
            self.mp3file = MP3(path, ID3=EasyID3)
        if self._extension.lower() == ".wav":
            self.mp3file = WAVE(path, ID3=EasyID3)

    def parse(self):
        self.analyze_track()
        self.update_tags()
        self.get_genre_from_artist()
        self.get_genre_from_label()
        self.get_genre_from_subgenres()

    def check_or_update_tag(self, tag, value):
        tag_value = self.get_tag_as_string(tag)
        if tag_value is None or tag_value != value:
            if tag_value is not None and value is not None and tag_value.title() == value.title():
                self.set_tag(tag, value + "_CapError")
                self.has_changes = True
                if s.debug:
                    print("cap error for ", tag)
                self.save_file()
            self.set_tag(tag, value)
            if s.debug:
                print("updated", tag, "to", value, "was", tag_value)
            self.has_changes = True

    def delete_tag(self, tag):
        if self.mp3file:
            if self.mp3file.get(tag):
                print("deleting", tag)
                self.mp3file.pop(tag)

    # Smart tag calculation
    def get_genre_from_artist(self):
        already_exists = False
        artists = self.artist()
        for artist in artists:
            for entry in artist_genre_mapping:
                if entry['name'] == artist:
                    for g in re.split(';|,/', self.genre()):
                        if g == entry['genre']:
                            already_exists = True
                    if not already_exists:
                        self.check_or_update_tag(GENRE, self.genre() + ';' + entry['genre'])
                        print("get_genre_from_artist", artist, self.genre())

    def get_genre_from_label(self):
        already_exists = False
        publisher = self.publisher()
        for entry in publisher_genre_mapping:
            if entry['name'] == publisher:
                for g in re.split(';|,/', self.genre()):
                    if g == entry['genre']:
                        already_exists = True
                if not already_exists:
                    self.check_or_update_tag(GENRE, self.genre() + ';' + entry['genre'])
                    print("get_genre_from_label", publisher, self.genre())

    def get_genre_from_subgenres(self):
        already_exists = False
        genres = self.get_tag_as_array(GENRE)
        for genre in genres:
            for entry in genressubgenres:
                if entry['name'] == genre:
                    for g in re.split(';|,/', self.genre()):
                        if g == entry['genre']:
                            already_exists = True
                    if not already_exists:
                        self.check_or_update_tag(GENRE, self.genre() + ';' + entry['genre'])
                        print("get_genre_from_subgenres", genre, self.genre())

    def calculate_copyright(self):
        publisher = self.publisher()
        date = self.date()
        year = str(date)[0:4]
        if publisher:
            if date:
                return publisher + " (" + year + ")"
            return self.publisher()
        return None

    def update_tags(self):
        self.check_or_update_tag(PUBLISHER, self._publisher)
        self.check_or_update_tag(CATALOG_NUMBER, self._catalog_number)
        self.check_or_update_tag(GENRE, self.genre(FORMAT.RECAPITALIZE))
        self.check_or_update_tag(ARTIST, parse_artist(self.artist()))
        self.check_or_update_tag(ALBUM_ARTIST, parse_artist(self.album_artist()))
        self.check_or_update_tag(COPYRIGHT, self.calculate_copyright())
        self.delete_tag(PUBLISHER_OLD)
        self.save_file()

    def save_file(self):
        if self.has_changes or s.rescan and not s.dryrun:
            if self.mp3file:
                self.mp3file.save()

    def get_tag(self, tag):
        if self.mp3file:
            return self.mp3file.get(tag)

    def get_tag_as_array(self, tag):
        value = self.get_tag_as_string(tag)
        return value.split(";")

    def get_tag_as_string(self, tag, format_tag=FORMAT.NONE):
        value = self.get_tag(tag)
        if value is None:
            return ""
        else:
            return to_semicolon_separated_tag(value, format_tag)

    def set_tag(self, tag, value):
        if self.mp3file:
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
        try:
            audio_file = librosa.load(self._path)
            y, sr = audio_file
            tempo = librosa.beat.beat_track(y=y, sr=sr)
            # noinspection PyTypeChecker
            self.check_or_update_tag(BPM, str(round(tempo[0][0])))
        except Exception as e:
            if s.debug:
                print('Failed to parse bpm for ' + self._path + str(e))

    # Getter wrappers
    def genre(self, format_tag=FORMAT.NONE):
        return self.get_tag_as_string(GENRE, format_tag)

    def bpm(self):
        return self.get_tag_as_string(BPM)

    def artist(self):
        return self.get_tag_as_string(ARTIST)

    def album_artist(self):
        return self.get_tag_as_string(ALBUM_ARTIST)

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
                except Exception as e:
                    print('Failed to parse ep ' + ep + ' ' + str(e))

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
                except Exception as e:
                    print('Failed to parse sub_folder ' + sub_folder + ' ' + str(e))

    def parse_ep(self, label, ep):
        files = glob.glob(
            self.settings.eps_folder_path + self.settings.delimiter + label + self.settings.delimiter + ep + self.settings.delimiter + "*.mp3") + glob.glob(
            self.settings.eps_folder_path + self.settings.delimiter + label + self.settings.delimiter + ep + self.settings.delimiter + "*.wav") + glob.glob(
            self.settings.eps_folder_path + self.settings.delimiter + label + self.settings.delimiter + ep + self.settings.delimiter + "*.flac")
        for song in files:
            try:
                self.parse_song(song)
            except KeyboardInterrupt:
                print('KeyboardInterrupt')
                sys.exit(1)
            except Exception as e:
                print('Failed to parse song ' + song + ' ' + str(e))

    def parse_song(self, path):
        song = LabelSong(path)
        # noinspection PyUnreachableCode
        if False:
            song.print()
