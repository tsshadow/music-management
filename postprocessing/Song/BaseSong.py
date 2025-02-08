import logging
import os

import librosa
import mutagen
from mutagen.apev2 import APEv2
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4
from mutagen.wave import WAVE

from data.DatabaseConnector import DatabaseConnector
from data.settings import Settings
from postprocessing.Song.Tag import Tag
from postprocessing.Song.Helpers import LookupTableHelper, FilterTableHelper
from postprocessing.Song.TagCollection import TagCollection
from postprocessing.constants import ARTIST, GENRE, WAVTags, MP4Tags, DATE, PARSED, CATALOG_NUMBER, PUBLISHER, \
    COPYRIGHT, ALBUM_ARTIST, BPM, MusicFileType, TITLE, MP3Tags, FLACTags, AACTags

s = Settings()
db_connector = DatabaseConnector()
artistGenreHelper = LookupTableHelper(
    table_name="artist_genre",
    key_column_name="artist",
    value_column_name="genre"
)

labelGenreHelper = LookupTableHelper(
    table_name="label_genre",
    key_column_name="label",
    value_column_name="genre"
)

subgenreGenreHelper = LookupTableHelper(
    table_name="subgenre_genre",
    key_column_name="subgenre",
    value_column_name="genre"
)

unique_genres = FilterTableHelper("genres", "genre")

class ExtensionNotSupportedException(Exception):
    pass



class BaseSong:

    def __init__(self, path):
        paths = path.rsplit(s.delimiter, 2)
        self._path = path
        self._filename = str(paths[-1])
        self._extension = os.path.splitext(self._filename)[1]
        music_file_classes = {
            ".mp3": lambda p: (MP3(p, ID3=EasyID3), MusicFileType.MP3),
            ".flac": lambda p: (FLAC(p), MusicFileType.FLAC),
            ".wav": lambda p: (WAVE(p), MusicFileType.WAV),
            ".m4a": lambda p: (MP4(p), MusicFileType.M4A),
            # AAC does not support tagging, use APEv2 instead.
            ".aac": lambda p: (APEv2(p), MusicFileType.AAC)
        }
        try:
            self.music_file, self.type = music_file_classes[self._extension.lower()](path)
        except KeyError:
            raise ExtensionNotSupportedException(f"{self._extension} is not supported")

        if self.type != MusicFileType.AAC:
            self.tag_collection = TagCollection(self.music_file.tags)
        else:
            self.tag_collection = TagCollection(self.music_file)
        if self.type == MusicFileType.FLAC:
            self.normalize_flac_tags()

    def normalize_flac_tags(self):
        new_tags = {}

        for tag, value in self.music_file.tags:
            upper_tag = tag.upper()
            if tag != upper_tag:
                logging.info("Normalized FLAC tag: %s -> %s", tag, upper_tag)
            new_tags[upper_tag] = value  # Store normalized tag names

        self.music_file.tags.clear()  # Clear original tags
        self.music_file.tags.update(new_tags)  # Update with normalized tags
        self.music_file.save()

    def parse_tags(self):
        if self.tag_collection.has_item(ARTIST):
            self.tag_collection.get_item(ARTIST).regex()
            self.tag_collection.get_item(ARTIST).special_recapitalize()
            self.tag_collection.get_item(ARTIST).strip()
        if self.tag_collection.has_item(ALBUM_ARTIST):
            self.tag_collection.get_item(ALBUM_ARTIST).regex()
            self.tag_collection.get_item(ALBUM_ARTIST).special_recapitalize()
            self.tag_collection.get_item(ALBUM_ARTIST).strip()
        if self.tag_collection.has_item(GENRE):
            self.tag_collection.get_item(GENRE).regex()
            self.tag_collection.get_item(GENRE).recapitalize()
            self.tag_collection.get_item(GENRE).strip()
            self.tag_collection.get_item(GENRE).sort()
            genres = self.tag_collection.get_item(GENRE).to_array()
            for genre in genres:
                if not unique_genres.exists(genre):
                    print(genre)





    def __del__(self):
        self.save_file()

    def update_tag(self, tag, value):
        if not value:
            return
        self.tag_collection.add(tag, value)

    def delete_tag(self, tag):
        if self.music_file and self.music_file.get(tag):
            self.music_file.pop(tag)
        if tag in self.tag_collection:
            self.tag_collection[tag].pop()

    def merge_and_sort_genres(self, existing_genres, new_genres):
        merged = list(set(existing_genres + new_genres))
        merged.sort()
        return merged

    def get_genre_from_artist(self):
        song_artists = self.tag_collection.get_item_as_array(ARTIST)
        song_genres = self.tag_collection.get_item_as_array(GENRE)
        for artist in song_artists:
            lookup_genres = artistGenreHelper.get(artist)
            if lookup_genres:
                song_genres = self.merge_and_sort_genres(song_genres, lookup_genres)
                self.tag_collection.add(GENRE, ";".join(song_genres))

    def get_genre_from_label(self):
        publisher = self.tag_collection.get_item_as_string(PUBLISHER)
        song_genres = self.tag_collection.get_item_as_array(GENRE)
        lookup_genres = labelGenreHelper.get(publisher)
        if lookup_genres:
            song_genres = self.merge_and_sort_genres(song_genres, lookup_genres)
            self.update_tag(GENRE, ";".join(song_genres))
    def get_genre_from_album_artist(self):
        publisher = self.tag_collection.get_item_as_string(ALBUM_ARTIST)
        song_genres = self.tag_collection.get_item_as_array(GENRE)
        lookup_genres = labelGenreHelper.get(publisher)
        if lookup_genres:
            song_genres = self.merge_and_sort_genres(song_genres, lookup_genres)
            self.update_tag(GENRE, ";".join(song_genres))


    def get_genre_from_subgenres(self):
        song_genres = self.tag_collection.get_item_as_array(GENRE)
        for genre in song_genres:
            lookup_genres = subgenreGenreHelper.get(genre)
            if lookup_genres:
                song_genres = self.merge_and_sort_genres(song_genres, lookup_genres)
                self.update_tag(GENRE, ";".join(song_genres))

    def sort_genres(self):
        self.tag_collection.get_item_as_array(GENRE).sort()

    def save_file(self):
        if hasattr(self, 'tag_collection'):
            changed = False
            for tag in self.tag_collection.get().values():
                if isinstance(tag, Tag) and tag.has_changes():
                    self.set_tag(tag)
                    changed = True
            if changed:
                self.music_file.save()
                logging.info(f"File saved: {self.path()}")

    def set_tag(self, tag: Tag):
        logging.info(f"Set tag {tag.tag} to {tag.to_string()} (was: {self.music_file.get(tag.tag)})")
        if self.music_file:
            if self.type == MusicFileType.MP3:
                self.music_file[tag.tag] = tag.to_string()
            elif self.type == MusicFileType.FLAC:
                self.music_file[FLACTags[tag.tag]] = tag.to_string()
            elif self.type == MusicFileType.AAC:
                self.music_file[AACTags[tag.tag]] = tag.to_string()
            elif self.type == MusicFileType.WAV:
                self.music_file.tags[WAVTags[tag.tag]] = mutagen.id3.TextFrame(encoding=3, text=[tag.to_string()])
            elif self.type == MusicFileType.M4A:
                self.music_file.tags[MP4Tags[tag.tag]] = str(tag.to_string())

    def analyze_track(self):
        try:
            audio_file = librosa.load(self._path)
            y, sr = audio_file
            tempo = librosa.beat.beat_track(y=y, sr=sr)
            self.update_tag(BPM, str(round(tempo[0][0])))
        except Exception as e:
            if s.debug:
                logging.info(f'Failed to parse bpm for {self.path()}: {str(e)}')

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
