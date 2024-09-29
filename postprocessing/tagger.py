from typing import Final
import glob
import re
import os
import sys

import librosa

from mutagen.easyid3 import EasyID3
from mutagen.wave import WAVE
from mutagen.flac import FLAC
from mutagen.mp3 import MP3

from data.settings import Settings
from data.genressubgenres import genressubgenres
from data.artistgenre import artist_genre_mapping
from data.publishergenre import publisher_genre_mapping

from enum import Enum

# global vars
s = Settings()
EasyID3.RegisterTextKey('publisher_old', 'TPUB')
EasyID3.RegisterTXXXKey('publisher', 'publisher')
EasyID3.RegisterTXXXKey('parsed', 'parsed')

# Constants
ARTIST_REGEX: Final = "\s(&|feat\.?|featuring|features|ft\.?|presenting|X|pres\.?|versus|vs\.?)\s"

# noinspection SpellCheckingInspection
CATALOG_NUMBER: Final = "CATALOGNUMBER"
PUBLISHER: Final = "PUBLISHER"
PUBLISHER_OLD: Final = "PUBLISHER_OLD"
DATE: Final = "DATE"
BPM: Final = "BPM"
COPYRIGHT: Final = "COPYRIGHT"
GENRE: Final = "GENRE"
ARTIST: Final = "ARTIST"
# noinspection SpellCheckingInspection
ALBUM_ARTIST: Final = "ALBUMARTIST"
PARSED: Final = "PARSED"


# Enumerations
class FormatEnum(Enum):
    NONE = 0
    RECAPITALIZE = 1


class SongTypeEnum(Enum):
    NONE = 0
    LABEL = 1
    YOUTUBE = 2
    SOUNDCLOUD = 3


def to_semicolon_separated_tag(tags, format_tag=FormatEnum.NONE):
    if len(tags) == 1:
        if format_tag == FormatEnum.NONE:
            return tags[0]
        elif format_tag == FormatEnum.RECAPITALIZE:
            return tags[0].title()
    if len(tags) > 1:
        parsed_tags = ""
        for tag in tags:
            for g in re.split(';|,/', tag):
                g = g.strip()
                if format_tag == FormatEnum.NONE:
                    parsed_tags += g + ";"
                elif format_tag == FormatEnum.RECAPITALIZE:
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
        self._catalog_number = ""  # no default

        if self._extension.lower() == ".flac":
            self.mp3file = FLAC(path)
        else:
            if self._extension.lower() == ".mp3":
                self.mp3file = MP3(path, ID3=EasyID3)
            else:
                if self._extension.lower() == ".wav":
                    self.mp3file = WAVE(path)
                else:
                    raise ("Cant find mp3 file for", path)

    def parse(self):
        # self.analyze_track()
        self.update_tags()
        self.get_genre_from_artist()
        self.get_genre_from_label()
        self.get_genre_from_subgenres()
        self.save_file()

    def check_or_update_tag(self, tag, value):
        if not value:
            return
        tag_value = self.get_tag_as_string(tag)
        if tag_value is None or tag_value != value:
            if tag_value is not None and value is not None and tag_value.title() == value.title():
                self.set_tag(tag, value + "_CapError")
                if s.debug:
                    print("cap error for ", tag)
                self.save_file()
            self.set_tag(tag, value)
            if s.debug:
                print("updated", tag, "to", value, "was", tag_value)

    def delete_tag(self, tag):
        if self.mp3file:
            if self.mp3file.get(tag):
                print("deleting", tag)
                self.mp3file.pop(tag)
                self.has_changes = True

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
        return None

    def update_tags(self):
        self.check_or_update_tag(PUBLISHER, self._publisher)
        self.check_or_update_tag(CATALOG_NUMBER, self._catalog_number)
        self.check_or_update_tag(GENRE, self.genre(FormatEnum.RECAPITALIZE))
        self.check_or_update_tag(ARTIST, parse_artist(self.artist()))
        self.check_or_update_tag(ALBUM_ARTIST, parse_artist(self.album_artist()))
        self.check_or_update_tag(COPYRIGHT, self.calculate_copyright())
        self.delete_tag(PUBLISHER_OLD)

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

    def get_tag_as_string(self, tag, format_tag=FormatEnum.NONE):
        value = self.get_tag(tag)
        if value is None:
            return ""
        else:
            return to_semicolon_separated_tag(value, format_tag)

    def set_tag(self, tag, value):
        if self.mp3file:
            self.mp3file[tag] = value
            self.has_changes = True

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
    def genre(self, format_tag=FormatEnum.NONE):
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

    def calculate_copyright(self):
        publisher = self.publisher()
        date = self.date()
        year = str(date)[0:4]
        if publisher:
            if date:
                return publisher + " (" + year + ")"
            return self.publisher()
        return None


class YoutubeSong(Song):
    def __init__(self, path):
        super().__init__(path)
        self._publisher = "Youtube"
        self._catalog_number = None
        paths = path.rsplit(s.delimiter, 2)
        self.check_or_update_tag(ALBUM_ARTIST, str(paths[1]))
        self.parse()

    def calculate_copyright(self):
        album_artist = self.album_artist()
        date = self.date()
        year = str(date)[0:4]
        if album_artist:
            if date:
                return album_artist + " (" + year + ")"
            return self.publisher()
        return None


class SoundcloudSong(Song):
    def __init__(self, path):
        super().__init__(path)
        self._publisher = "Soundcloud"
        self._catalog_number = None
        paths = path.rsplit(s.delimiter, 2)
        self.check_or_update_tag(ALBUM_ARTIST, str(paths[1]))
        self.parse()

    def calculate_copyright(self):
        album_artist = self.album_artist()
        date = self.date()
        year = str(date)[0:4]
        if album_artist:
            if date:
                return album_artist + " (" + year + ")"
            return self.publisher()
        return None


class Tagger:
    def __init__(self):
        self.rescan = None

    def tag(self):
        label_folders = [f for f in os.listdir(s.eps_folder_path) if
                         not os.path.isfile(os.path.join(s.eps_folder_path, f))]
        for label in label_folders:
            self.parse_folder(s.eps_folder_path + s.delimiter + label, SongTypeEnum.LABEL)

        soundcloud_folder = s.music_folder_path + s.delimiter + "Soundcloud"
        soundcloud_channel_folders = [f for f in os.listdir(soundcloud_folder) if
                                      not os.path.isfile(os.path.join(soundcloud_folder, f))]
        for soundcloud_channel_folder in soundcloud_channel_folders:
            self.parse_folder(
                s.music_folder_path + s.delimiter + "Soundcloud" + s.delimiter + soundcloud_channel_folder,
                SongTypeEnum.SOUNDCLOUD)

        youtube_folder = s.music_folder_path + s.delimiter + "Youtube"
        youtube_channel_folders = [f for f in os.listdir(youtube_folder) if
                                   not os.path.isfile(os.path.join(youtube_folder, f))]
        for youtube_channel_folder in youtube_channel_folders:
            self.parse_folder(
                s.music_folder_path + s.delimiter + "Youtube" + s.delimiter + youtube_channel_folder,
                SongTypeEnum.YOUTUBE)

    def parse_folder(self, folder, song_type):
        folders = [f for f in os.listdir(folder) if
                   not os.path.isfile(os.path.join(folder, f))]
        files = glob.glob(
            folder + s.delimiter + "*.mp3") + glob.glob(
            folder + s.delimiter + "*.wav") + glob.glob(
            folder + s.delimiter + "*.flac")

        for file in files:
            try:
                self.parse_song(file, song_type)
            except KeyboardInterrupt:
                print('KeyboardInterrupt')
                sys.exit(1)
            except SystemExit:
                sys.exit(2)
            except Exception as e:
                print('Failed to parse song ' + file + ' ' + str(e))
        for sub_folder in folders:
            if sub_folder[0] != '_':
                try:
                    self.parse_folder(folder + s.delimiter + sub_folder, song_type)
                except KeyboardInterrupt:
                    print('KeyboardInterrupt')
                    sys.exit(1)
                except SystemExit:
                    sys.exit(2)
                except Exception as e:
                    print('Failed to parse folder ' + sub_folder + ' ' + str(e))

    def parse_song(self, path, song_type):
        if song_type == SongTypeEnum.LABEL:
            song = LabelSong(path)
        if song_type == SongTypeEnum.YOUTUBE:
            song = YoutubeSong(path)
        if song_type == SongTypeEnum.SOUNDCLOUD:
            song = SoundcloudSong(path)
        # noinspection PyUnreachableCode
        # song.print()
