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

from data.settings import Settings
from postprocessing.Song.Tag import Tag
from postprocessing.Song.Helpers import LookupTableHelper
from postprocessing.Song.TagCollection import TagCollection
from postprocessing.constants import ARTIST, GENRE, WAVTags, MP4Tags, DATE, PARSED, CATALOG_NUMBER, PUBLISHER, \
    COPYRIGHT, ALBUM_ARTIST, BPM, ARTIST_REGEX, FormatEnum, MusicFileType, TITLE

s = Settings()
artistGenreHelper = LookupTableHelper('data/artist-genre.txt')
labelGenreHelper = LookupTableHelper('data/label-genre.txt')
subgenreGenreHelper = LookupTableHelper('data/subgenres-genres.txt')


class ExtensionNotSupportedException(Exception):
    pass


class BaseSong:
    def special_print(self, *arg):
        if self.new_line:
            print()
            self.new_line = False
        print(arg)

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

    def __init__(self, path):
        # Setup member variables
        self.new_line = True
        self.has_changes = False
        self.tags: TagCollection
        paths = path.rsplit(s.delimiter, 2)
        self._path = path
        self._filename = str(paths[-1])
        self._extension = os.path.splitext(self._filename)[1]
        self._publisher = None  # no default
        self._catalog_number = ""  # no default
        if self._extension.lower() == ".mp3":
            self.music_file = MP3(path, ID3=EasyID3)
            self.type = MusicFileType.MP3
            self.tag_collection = TagCollection(self.music_file.tags)
        elif self._extension.lower() == ".flac":
            self.music_file = FLAC(path)
            self.type = MusicFileType.FLAC
            self.tag_collection = TagCollection(self.music_file.tags)
        elif self._extension.lower() == ".wav":
            raise ExtensionNotSupportedException(".wav currently not supported")
            self.music_file = WAVE(path)
            self.type = MusicFileType.WAV
        elif self._extension.lower() == ".m4a":
            raise ExtensionNotSupportedException(".m4a currently not supported")
            self.music_file = MP4(path)
            self.type = MusicFileType.M4A
        else:
            raise Exception("Cant find mp3 file for", path)

    def parse_tags(self):
        if self.tag_collection.has_item(ARTIST):
            self.tag_collection.get_item(ARTIST).regex()
            self.tag_collection.get_item(ARTIST).special_recapitalize()
        if self.tag_collection.has_item(ALBUM_ARTIST):
            self.tag_collection.get_item(ALBUM_ARTIST).regex()
            self.tag_collection.get_item(ALBUM_ARTIST).special_recapitalize()
        if self.tag_collection.has_item(GENRE):
            self.tag_collection.get_item(GENRE).recapitalize()

    def __del__(self):
        self.save_file()

    def update_tag(self, tag, value):
        if not value:
            return
        self.tag_collection.add(tag, value)

    def delete_tag(self, tag):
        if self.music_file:
            if self.music_file.get(tag):
                # self.special_print("deleting", tag)
                self.music_file.pop(tag)
                self.has_changes = True
            self.tag_collection[tag].pop()

    def get_genre_from_artist(self):
        song_artists = self.tag_collection.get_item_as_array(ARTIST)
        song_genres = self.tag_collection.get_item_as_array(GENRE)
        for artist in song_artists:
            lookup_genres = artistGenreHelper.get(artist)
            if lookup_genres:
                merged_array = list(set(song_genres + lookup_genres))
                merged_array.sort()
                self.tag_collection.add(GENRE, ";".join(merged_array))
                song_genres = merged_array

    def get_genre_from_label(self):
        publisher = self.tag_collection.get_item_as_string(PUBLISHER)
        song_genres = self.tag_collection.get_item_as_array(GENRE)
        lookup_genres = labelGenreHelper.get(publisher)
        if lookup_genres is not None:
            merged_array = list(set(song_genres + lookup_genres))
            merged_array.sort()
            self.update_tag(GENRE, ";".join(merged_array))

    def get_genre_from_subgenres(self):
        song_genres = self.tag_collection.get_item_as_array(GENRE)
        for genre in song_genres:
            lookup_genres = subgenreGenreHelper.get(genre)
            if lookup_genres is not None:
                merged_array = list(set(song_genres + lookup_genres))
                merged_array.sort()
                self.update_tag(GENRE, ";".join(merged_array))
                song_genres = merged_array

    def sort_genres(self):
        self.tag_collection.get_item_as_array(GENRE).sort()

    def calculate_copyright(self):
        return None

    def save_file(self):
        if not s.dryrun and hasattr(self, 'tag_collection'):
            for tag in self.tag_collection.get().values():
                if isinstance(tag, Tag):
                    # if tag.has_capitalization_error():
                    #     self.set_tag(Tag(tag.tag, ['temp']))
                    #     self.music_file.save()
                    #     self.set_tag(tag)
                    #     self.music_file.save()
                    if tag.has_changes():
                        self.set_tag(tag)
                        self.music_file.save()
                        print("save")
                else:
                    print("Failed to save tag:", tag)

    def get_tag(self, tag):
        if self.music_file:
            if self.type == MusicFileType.MP3 or self.type == MusicFileType.FLAC:
                return self.music_file.get(tag)
            elif self.type == MusicFileType.WAV:
                try:
                    value = self.music_file.tags[WAVTags[tag]]
                except Exception as e:
                    self.special_print(e)
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

        # def get_tag_as_array(self, tag):
        #     value = self.get_tag_as_string(tag)
        #     return value.split(";")

        # def get_tag_as_string(self, tag, format_tag=FormatEnum.NONE):
        #     value = self.get_tag(tag)
        #     if value is None:
        #         return ""
        #     else:
        #         return self.to_semicolon_separated_tag(value, format_tag)

    def set_tag(self, tag: Tag):
        print("set tag", tag.tag, tag.to_string())
        if self.music_file:
            if self.type == MusicFileType.MP3 or self.type == MusicFileType.FLAC:
                print("was:", self.music_file.get(tag.tag))
                self.music_file[tag.tag] = tag.to_string()
            elif self.type == MusicFileType.WAV:
                try:
                    self.special_print(self.music_file.tags[WAVTags[tag]])
                except Exception as e:
                    print(e)
                    self.music_file.tags.add(TXXX(encoding=3, text=[tag.to_string()], desc=WAVTags[tag]))
                self.music_file.tags[WAVTags[tag]] = mutagen.id3.TextFrame(encoding=3, text=[tag.to_string()])
                self.special_print(' set ', self.music_file.tags[WAVTags[tag]])
            elif self.type == MusicFileType.M4A:
                self.music_file.tags[MP4Tags[tag]] = str(tag.to_string())
            self.has_changes = True

    def analyze_track(self):
        try:
            audio_file = librosa.load(self._path)
            y, sr = audio_file
            tempo = librosa.beat.beat_track(y=y, sr=sr)
            # noinspection PyTypeChecker
            self.update_tag(BPM, str(round(tempo[0][0])))
        except Exception as e:
            if s.debug:
                self.special_print('Failed to parse bpm for ' + self._path + str(e))

        # Getter wrappers

    def genre(self):
        return self.tag_collection.get_item_as_string(GENRE)

    def bpm(self):
        return self.tag_collection.get_item_as_string(BPM)

    def artist(self):
        return self.tag_collection.get_item_as_string(ARTIST)

    def title(self):
        return self.tag_collection.get_item_as_string(TITLE)

    def album_artist(self):
        return self.tag_collection.get_item_as_string(ALBUM_ARTIST)

    def copyright(self):
        return self.tag_collection.get_item_as_string(COPYRIGHT)

    def publisher(self):
        return self.tag_collection.get_item_as_string(PUBLISHER)

    def catalog_number(self):
        return self.tag_collection.get_item_as_string(CATALOG_NUMBER)

    def filename(self):
        return self._filename

    def path(self):
        return self._path

    def extension(self):
        return self._extension

    def parsed(self):
        return self.tag_collection.get_item_as_string(PARSED)

    def date(self):
        return self.tag_collection.get_item_as_string(DATE)
