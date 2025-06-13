import logging
import os
import re

import librosa
import mutagen
from mutagen.easyid3 import EasyID3
from mutagen.flac import FLAC
from mutagen.mp3 import MP3
from mutagen.mp4 import MP4, MP4StreamInfoError
from mutagen.wave import WAVE

from data.settings import Settings
from postprocessing.Song.Tag import Tag
from postprocessing.Song.TagCollection import TagCollection
from postprocessing.Song.rules.AnalyzeBpmRule import AnalyzeBpmRule
from postprocessing.Song.rules.CheckArtistRule import CheckArtistRule
from postprocessing.Song.rules.NormalizeFlacTagsRule import NormalizeFlacTagsRule
from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import ARTIST, GENRE, WAVTags, MP4Tags, DATE, FESTIVAL, PARSED, CATALOG_NUMBER, \
    PUBLISHER, COPYRIGHT, ALBUM_ARTIST, BPM, MusicFileType, TITLE, FLACTags, ARTIST_REGEX, REMIXER

LOG_FILE = "broken-files.log"
s = Settings()

analyze_bpm = False

class ExtensionNotSupportedException(Exception):
    """Raised when an unsupported music file extension is encountered."""
    pass


def log_broken_file(pad: str):
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(pad + "\n")


class BaseSong:
    """
    Represents a single audio file and its associated metadata.

    Supports MP3, FLAC, WAV, M4A, and AAC (partial).
    Provides methods to read, clean, update, and save tags.
    """

    def __init__(self, path, extra_info=None):
        """
        Initializes the BaseSong object by loading the file and its tags.

        Args:
            path (str): Path to the audio file.
        """
        self.rules: list[TagRule] = []
        paths = path.rsplit(s.delimiter, 2)
        self._path: str = path
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
        except MP4StreamInfoError:
            print("MP4StreamInfoError" + path)
            try:
                os.remove(path)
                print("deleted broken file: " + path)
                log_broken_file(path)
                return
            except Exception as e:
                print("Kon bestand niet verwijderen:", e)

        if self.type == MusicFileType.WAV and self.music_file.tags is None:
            self.music_file.add_tags()

        self.tag_collection = TagCollection(
            self.music_file.tags if self.type != MusicFileType.AAC else self.music_file
        )

        if extra_info:
            self._apply_extra_info(extra_info)

        if self.type == MusicFileType.FLAC:
            NormalizeFlacTagsRule().apply(self)
        if analyze_bpm:
            self.rules.append(AnalyzeBpmRule())

    def delete_tag(self, tag):
        """Removes a tag from both the tag collection and file if present."""
        if self.music_file and self.music_file.get(tag):
            self.music_file.pop(tag)
        if tag in self.tag_collection.get():
            self.tag_collection.get()[tag].remove()

    def split_artists(self, artist_str: str) -> list[str]:
        raw = re.sub(ARTIST_REGEX, ";", artist_str)
        return [name.strip() for name in raw.split(";") if name.strip()]

    def merge_and_sort_genres(self, a, b):
        """Merges and sorts two lists of genres, removing duplicates."""
        return sorted(set(a + b))

    def sort_genres(self):
        """Sorts the genre tag array alphabetically if the tag exists."""
        if self.tag_collection.has_item(GENRE):
            genres = self.tag_collection.get_item(GENRE)
            genres.value.sort()

    def save_file(self):
        if not hasattr(self, 'tag_collection'):
            return

        for tag in self.tag_collection.get().values():
            if isinstance(tag, Tag) and tag.has_changes():
                self.set_tag(tag)
                self.music_file.save()
                logging.info(f"File saved: {self.path()}")
                return

    def set_tag(self, tag: Tag):
        """Sets a tag on the underlying music file based on type."""
        logging.info(f"Set tag {tag.tag} to {tag.to_string()} (was: {self.music_file.get(tag.tag)})")

        value = tag.to_string()

        if self.type == MusicFileType.MP3:
            self.music_file[tag.tag] = value

        elif self.type == MusicFileType.FLAC:
            flac_key = FLACTags.get(tag.tag)
            if flac_key:
                self.music_file[flac_key] = value

        elif self.type == MusicFileType.WAV:
            wav_key = WAVTags.get(tag.tag)
            if wav_key:
                self.music_file.tags[wav_key] = mutagen.id3.TextFrame(encoding=3, text=[value])

        elif self.type == MusicFileType.M4A:
            mp4_key = MP4Tags.get(tag.tag)
            if mp4_key:
                self.music_file.tags[mp4_key] = value
            else:
                # Fallback for LMS-style custom tags
                from mutagen.mp4 import MP4FreeForm
                custom_key = f"----:com.apple.iTunes:{tag.tag.upper()}"
                self.music_file.tags[custom_key] = [MP4FreeForm(value.encode('utf-8'))]

    def length(self):
        try:
            if hasattr(self.music_file, "info") and hasattr(self.music_file.info, "length"):
                return self.music_file.info.length
            logging.warning(f"Could not retrieve length for: {self.path()}")
        except Exception as e:
            logging.warning(f"Error retrieving length for {self.path()}: {e}")
        return None

    def _apply_extra_info(self, info):
        """
        Apply extra metadata from yt-dlp dump to tag collection.
        """
        # Prefer "artists", fallback to "artist", then "uploader"
        artist = (
            info.get("artists", [None])[0] if isinstance(info.get("artists"), list)
            else info.get("artist")
        )
        if artist:
            self.tag_collection.set_item(ARTIST, artist)

    # Property-style accessors for common metadata fields
    def album(self):
        return self.tag_collection.get_item_as_string(ALBUM)

    def album_artist(self):
        return self.tag_collection.get_item_as_string(ALBUM_ARTIST)

    def artist(self):
        return self.tag_collection.get_item_as_string(ARTIST)

    def artists(self):
        return self.tag_collection.get_item_as_array(ARTIST)

    def bpm(self):
        return self.tag_collection.get_item_as_string(BPM)

    def catalog_number(self):
        return self.tag_collection.get_item_as_string(CATALOG_NUMBER)

    def copyright(self):
        return self.tag_collection.get_item_as_string(COPYRIGHT)

    def date(self):
        return self.tag_collection.get_item_as_string(DATE)

    def festival(self):
        return self.tag_collection.get_item_as_string(FESTIVAL)

    def genre(self):
        return self.tag_collection.get_item_as_string(GENRE)

    def genres(self):
        return self.tag_collection.get_item_as_array(GENRE)

    def parsed(self):
        return self.tag_collection.get_item_as_string(PARSED)

    def publisher(self):
        return self.tag_collection.get_item_as_string(PUBLISHER)

    def remixer(self):
        return self.tag_collection.get_item_as_string(REMIXER)

    def remixers(self):
        return self.tag_collection.get_item_as_array(REMIXER)

    def title(self):
        return self.tag_collection.get_item_as_string(TITLE)

    def track_number(self):
        return self.tag_collection.get_item_as_string(TRACK_NUMBER)

    # File-related properties (not tags, but useful for access)
    def filename(self):
        return self._filename

    def path(self):
        return self._path

    def extension(self):
        return self._extension

    def run_all_rules(self):
        for rule in self.rules:
            rule.apply(self)

    def __del__(self):
        """Ensure changes are saved when the object is deleted."""
        self.save_file()

