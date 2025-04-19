import logging
import os
import re

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
from postprocessing.Song.Helpers.LookupTableHelper import LookupTableHelper
from postprocessing.Song.Helpers.FilterTableHelper import FilterTableHelper
from postprocessing.Song.Helpers.FestivalHelper import FestivalHelper
from postprocessing.Song.Helpers.TableHelper import TableHelper
from postprocessing.Song.Tag import Tag
from postprocessing.Song.TagCollection import TagCollection
from postprocessing.constants import ARTIST, GENRE, WAVTags, MP4Tags, DATE, FESTIVAL, PARSED, CATALOG_NUMBER, \
    PUBLISHER, COPYRIGHT, ALBUM_ARTIST, BPM, MusicFileType, TITLE, MP3Tags, FLACTags, AACTags

s = Settings()

# Helper instances
db_helpers = {
    "artist_genre": LookupTableHelper("artist_genre", "artist", "genre"),
    "label_genre": LookupTableHelper("label_genre", "label", "genre"),
    "subgenre_genre": LookupTableHelper("subgenre_genre", "subgenre", "genre"),
    "artists": TableHelper("artists", "name"),
    "festival": FestivalHelper(),
    "genres": FilterTableHelper("genres", "genre", "corrected_genre")
}


class ExtensionNotSupportedException(Exception):
    """Raised when an unsupported music file extension is encountered."""
    pass


class BaseSong:
    """
    Represents a single audio file and its associated metadata.

    Supports MP3, FLAC, WAV, M4A, and AAC (partial).
    Provides methods to read, clean, update, and save tags.
    """

    def __init__(self, path):
        """
        Initializes the BaseSong object by loading the file and its tags.

        Args:
            path (str): Path to the audio file.
        """
        paths = path.rsplit(s.delimiter, 2)
        self._path = path
        self._filename = str(paths[-1])
        self._extension = os.path.splitext(self._filename)[1].lower()

        music_file_classes = {
            ".mp3": lambda p: (MP3(p, ID3=EasyID3), MusicFileType.MP3),
            ".flac": lambda p: (FLAC(p), MusicFileType.FLAC),
            ".wav": lambda p: (WAVE(p), MusicFileType.WAV),
            ".m4a": lambda p: (MP4(p), MusicFileType.M4A)
            # ".aac": lambda p: (APEv2(p), MusicFileType.AAC)  # Non-standard fallback

        }

        try:
            self.music_file, self.type = music_file_classes[self._extension](path)
        except KeyError:
            raise ExtensionNotSupportedException(f"{self._extension} is not supported")

        if self.type == MusicFileType.WAV and self.music_file.tags is None:
            self.music_file.add_tags()

        self.tag_collection = TagCollection(
            self.music_file.tags if self.type != MusicFileType.AAC else self.music_file
        )

        if self.type == MusicFileType.FLAC:
            self.normalize_flac_tags()

    def normalize_flac_tags(self):
        """Ensures all FLAC tag keys are uppercase and updates the file."""
        new_tags = {
            tag.upper(): value for tag, value in self.music_file.tags
        }
        self.music_file.tags.clear()
        self.music_file.tags.update(new_tags)
        self.music_file.save()

    def parse_tags(self):
        """Performs tag cleaning and genre filtering using lookup and filter helpers."""
        for field in [ARTIST, ALBUM_ARTIST]:
            if self.tag_collection.has_item(field):
                tag = self.tag_collection.get_item(field)
                tag.regex()
                tag.special_recapitalize()
                tag.strip()

        if self.tag_collection.has_item(GENRE):
            genre_tag = self.tag_collection.get_item(GENRE)
            genre_tag.regex()
            genre_tag.recapitalize()
            genre_tag.strip()
            genre_tag.sort()

            genres = genre_tag.to_array()
            valid_genres = []
            for genre in genres:
                if db_helpers["genres"].exists(genre):
                    valid_genres.append(genre)
            genre_tag.set(valid_genres)

    def update_tag(self, tag, value):
        """Adds or updates a tag value."""
        if value:
            self.tag_collection.add(tag, value)

    def delete_tag(self, tag):
        """Removes a tag from both the tag collection and file if present."""
        if self.music_file and self.music_file.get(tag):
            self.music_file.pop(tag)
        if tag in self.tag_collection.get():
            self.tag_collection.get()[tag].remove()

    def get_genre_from_artist(self):
        """Attempts to enrich genre based on known artist-genre mapping."""
        for artist in self.tag_collection.get_item_as_array(ARTIST):
            genres = db_helpers["artist_genre"].get(artist)
            if genres:
                merged = self.merge_and_sort_genres(
                    self.tag_collection.get_item_as_array(GENRE), genres
                )
                self.update_tag(GENRE, ";".join(merged))

    def get_genre_from_label(self):
        """Attempts to enrich genre based on the publisher (label)."""
        publisher = self.tag_collection.get_item_as_string(PUBLISHER)
        genres = db_helpers["label_genre"].get(publisher)
        if genres:
            merged = self.merge_and_sort_genres(
                self.tag_collection.get_item_as_array(GENRE), genres
            )
            self.update_tag(GENRE, ";".join(merged))

    def get_genre_from_album_artist(self):
        """Enriches genre using the album artist field."""
        artist = self.tag_collection.get_item_as_string(ALBUM_ARTIST)
        genres = db_helpers["label_genre"].get(artist)
        if genres:
            merged = self.merge_and_sort_genres(
                self.tag_collection.get_item_as_array(GENRE), genres
            )
            self.update_tag(GENRE, ";".join(merged))

    def get_genre_from_subgenres(self):
        """Maps existing genres to broader ones using subgenre lookup."""
        current_genres = self.tag_collection.get_item_as_array(GENRE)
        for genre in current_genres:
            lookup = db_helpers["subgenre_genre"].get(genre)
            if lookup:
                merged = self.merge_and_sort_genres(current_genres, lookup)
                self.update_tag(GENRE, ";".join(merged))

    def get_artist_from_title(self):
        """Attempts to extract artist from title using regex and corrects capitalization."""
        title = self.tag_collection.get_item_as_string(TITLE)
        if not title:
            return

        match = re.search(r"\\((.*?)\\s+(edit|remix)\\)", title, re.IGNORECASE)
        if match:
            artist = match.group(1)
            canonical = db_helpers["artists"].get_canonical(artist)
            existing = self.tag_collection.get_item_as_array(ARTIST)
            if canonical not in existing:
                art_tag = self.tag_collection.get_item(ARTIST)
                before = art_tag.to_string()
                changed = art_tag.changed
                art_tag.add(canonical)
                art_tag.special_recapitalize()
                art_tag.deduplicate()
                if before == art_tag.to_string():
                    art_tag.changed = changed

    def get_date_festival_from_title(self):
        """Extracts festival and date metadata from the title tag using fuzzy matching."""
        title = self.tag_collection.get_item_as_string(TITLE)
        if not title or (self.length() and self.length() < 600):
            return

        info = db_helpers["festival"].get(title)
        if info:
            if "festival" in info:
                self.update_tag(FESTIVAL, info["festival"])
            if "date" in info:
                self.update_tag(DATE, info["date"])

    def merge_and_sort_genres(self, a, b):
        """Merges and sorts two lists of genres, removing duplicates."""
        return sorted(set(a + b))

    def sort_genres(self):
        """Sorts the genre tag array alphabetically if the tag exists."""
        if self.tag_collection.has_item(GENRE):
            genres = self.tag_collection.get_item(GENRE)
            genres.value.sort()

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
        """Sets a tag on the underlying music file based on type."""
        logging.info(f"Set tag {tag.tag} to {tag.to_string()} (was: {self.music_file.get(tag.tag)})")
        if self.type == MusicFileType.MP3:
            self.music_file[tag.tag] = tag.to_string()
        elif self.type == MusicFileType.FLAC:
            self.music_file[FLACTags[tag.tag]] = tag.to_string()
        elif self.type == MusicFileType.WAV:
            self.music_file.tags[WAVTags[tag.tag]] = mutagen.id3.TextFrame(encoding=3, text=[tag.to_string()])
        elif self.type == MusicFileType.M4A:
            self.music_file.tags[MP4Tags[tag.tag]] = str(tag.to_string())

    def analyze_track(self):
        """Uses librosa to estimate BPM and updates the BPM tag."""
        try:
            y, sr = librosa.load(self._path)
            tempo, _ = librosa.beat.beat_track(y=y, sr=sr)
            self.update_tag(BPM, str(round(tempo)))
        except Exception as e:
            if s.debug:
                logging.info(f"Failed to parse bpm for {self.path()}: {str(e)}")

    # Property-style accessors for common metadata fields
    def genre(self): return self.tag_collection.get_item_as_string(GENRE)
    def bpm(self): return self.tag_collection.get_item_as_string(BPM)
    def artist(self): return self.tag_collection.get_item_as_string(ARTIST)
    def title(self): return self.tag_collection.get_item_as_string(TITLE)
    def album_artist(self): return self.tag_collection.get_item_as_string(ALBUM_ARTIST)
    def copyright(self): return self.tag_collection.get_item_as_string(COPYRIGHT)
    def publisher(self): return self.tag_collection.get_item_as_string(PUBLISHER)
    def catalog_number(self): return self.tag_collection.get_item_as_string(CATALOG_NUMBER)
    def filename(self): return self._filename
    def path(self): return self._path
    def extension(self): return self._extension
    def parsed(self): return self.tag_collection.get_item_as_string(PARSED)
    def date(self): return self.tag_collection.get_item_as_string(DATE)
    def length(self):
        try:
            if hasattr(self.music_file, "info") and hasattr(self.music_file.info, "length"):
                return self.music_file.info.length
            logging.warning(f"Could not retrieve length for: {self.path()}")
        except Exception as e:
            logging.warning(f"Error retrieving length for {self.path()}: {e}")
        return None

    def __del__(self):
        """Ensure changes are saved when the object is deleted."""
        self.save_file()