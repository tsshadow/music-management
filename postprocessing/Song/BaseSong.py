import os
import re

import librosa
import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.id3 import TXXX
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

from data.artistgenre import artist_genre_mapping
from data.genressubgenres import genressubgenres
from data.publishergenre import publisher_genre_mapping
from data.settings import Settings
from postprocessing.constants import ARTIST, GENRE, WAVTags, MP4Tags, DATE, PARSED, CATALOG_NUMBER, PUBLISHER, \
    COPYRIGHT, ALBUM_ARTIST, BPM, ARTIST_REGEX, FormatEnum, MusicFileType

s = Settings()


class BaseSong:
    @staticmethod
    def to_semicolon_separated_tag(self, tags, format_tag=FormatEnum.NONE):
        if len(tags) == 1:
            if tags[0] is None:
                return ""
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

    def parse_artist(self, artist):
        parsed = re.sub(ARTIST_REGEX, ";", artist)
        return parsed

    def __init__(self, path):
        # Setup member variables
        self.has_changes = False
        paths = path.rsplit(s.delimiter, 2)
        self._path = path
        self._filename = str(paths[-1])
        self._extension = os.path.splitext(self._filename)[1]
        self._publisher = None  # no default
        self._catalog_number = ""  # no default
        if self._extension.lower() == ".mp3":
            self.music_file = MP3(path, ID3=EasyID3)
            self.type = MusicFileType.MP3
        elif self._extension.lower() == ".flac":
            self.music_file = FLAC(path)
            self.type = MusicFileType.FLAC
        elif self._extension.lower() == ".wav":
            self.music_file = WAVE(path)
            self.type = MusicFileType.WAV
            raise Exception("WAV file not supported")
        elif self._extension.lower() == ".m4a":
            self.music_file = MP4(path)
            self.type = MusicFileType.M4A
        else:
            raise Exception("Cant find mp3 file for", path)

    def parse(self):
        # self.analyze_track()
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
                global print_new_line
                if print_new_line:
                    print("\n")
                    print_new_line = False
                print("updated", tag, "to", value, "was", tag_value)
            self.save_file()

    def delete_tag(self, tag):
        if self.music_file:
            if self.music_file.get(tag):
                # print("deleting", tag)
                self.music_file.pop(tag)
                self.has_changes = True

    # Smart tag calculation
    def get_genre_from_artist(self):
        already_exists = False
        artists = self.get_tag_as_array(ARTIST)
        for artist in artists:
            if artist in artist_genre_mapping:
                for g in re.split(';|,/', self.genre()):
                    if g == artist_genre_mapping[artist]:
                        already_exists = True
                if not already_exists:
                    if len(self.genre()) == 0:
                        self.check_or_update_tag(GENRE, artist_genre_mapping[artist])
                    else:
                        self.check_or_update_tag(GENRE, self.genre() + ';' + artist_genre_mapping[artist])
                    print("get_genre_from_artist", artist, self.genre())

    def get_genre_from_label(self):
        already_exists = False
        publisher = self.publisher()
        if publisher in publisher_genre_mapping:
            for g in re.split(';|,/', self.genre()):
                if g == publisher_genre_mapping[publisher]:
                    already_exists = True
            if not already_exists:
                if len(self.genre() == 0):
                    self.check_or_update_tag(artist_genre_mapping[publisher])
                else:
                    self.check_or_update_tag(GENRE, self.genre() + ';' + publisher_genre_mapping[publisher])
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
                        if len(self.genre()) == 0:
                            self.check_or_update_tag(GENRE, entry['genre'])
                        else:
                            self.check_or_update_tag(GENRE, self.genre() + ';' + entry['genre'])
                        print("get_genre_from_subgenres", genre, self.genre())

    def calculate_copyright(self):
        return None

    def save_file(self):
        if self.has_changes or s.rescan and not s.dryrun:
            if self.music_file:
                self.music_file.save()

    def get_tag(self, tag):
        if self.music_file:
            if self.type == MusicFileType.MP3 or self.type == MusicFileType.FLAC:
                return self.music_file.get(tag)
            elif self.type == MusicFileType.WAV:
                try:
                    value = self.music_file.tags[WAVTags[tag]]
                except Exception as e:
                    print(e)
                    return None
                return value.text
            elif self.type == MusicFileType.M4A:
                try:
                    value = self.music_file.tags[MP4Tags[tag]]
                    if len(value[0]) == 1:  # string
                        return [value]
                    else:  # array
                        return value
                except:
                    return None

    def get_tag_as_array(self, tag):
        value = self.get_tag_as_string(tag)
        return value.split(";")

    def get_tag_as_string(self, tag, format_tag=FormatEnum.NONE):
        value = self.get_tag(tag)
        if value is None:
            return ""
        else:
            return self.to_semicolon_separated_tag(value, format_tag)

    def set_tag(self, tag, value):
        if self.music_file:
            if self.type == MusicFileType.MP3 or self.type == MusicFileType.FLAC:
                self.music_file[tag] = value
            elif self.type == MusicFileType.WAV:
                try:
                    print(self.music_file.tags[WAVTags[tag]])
                except Exception as e:
                    print(e)
                    self.music_file.tags.add(TXXX(encoding=3, text=[value], desc=WAVTags[tag]))
                self.music_file.tags[WAVTags[tag]] = mutagen.id3.TextFrame(encoding=3, text=[value])
                print(' set ', self.music_file.tags[WAVTags[tag]])
            elif self.type == MusicFileType.M4A:
                self.music_file.tags[MP4Tags[tag]] = str(value)
            self.has_changes = True

    def print(self):
        if s.debug:
            # print("\n")
            # print("path           ", self.path())
            # print("filename       ", self.filename())
            # print("extension      ", self.extension())
            # print("genre          ", self.genre())
            # print("artist         ", self.artist())
            # print("album_artist         ", self.album_artist())
            # print("copyright      ", self.copyright())
            # print("publisher      ", self.publisher())
            # print("catalog_number ", self.catalog_number())
            # print("bpm            ", self.bpm())
            # print("\n\n")
            pass

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
