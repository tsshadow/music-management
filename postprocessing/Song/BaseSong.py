import logging
import os
import pathlib

import librosa
import mutagen
from mutagen.aac import AAC
from mutagen.apev2 import APEv2
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
from postprocessing.Song.UniqueTagHandler import UniqueTagHandler, TitleCaseTagChecker
from postprocessing.constants import ARTIST, GENRE, WAVTags, MP4Tags, DATE, PARSED, CATALOG_NUMBER, PUBLISHER, \
    COPYRIGHT, ALBUM_ARTIST, BPM, MusicFileType, TITLE, MP3Tags, FLACTags, AACTags

s = Settings()
artistGenreHelper = LookupTableHelper('data/artist-genre.txt')
labelGenreHelper = LookupTableHelper('data/label-genre.txt')
subgenreGenreHelper = LookupTableHelper('data/subgenres-genres.txt')


class ExtensionNotSupportedException(Exception):
    pass


uniqueArtists = TitleCaseTagChecker("Artists", "data/artists.txt", "data/ignored_artists.txt")
uniqueGenres = UniqueTagHandler("Genres", "data/genres.txt", "data/ignored_genres.txt")
uniqueAlbumArtists = TitleCaseTagChecker("Album Artists", "data/artists.txt", "data/ignored_artists.txt")


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
            for tag in self.music_file.tags:
                if tag[0] != tag[0].upper():
                    val = self.music_file.tags[tag[0]]
                    self.music_file[tag[0]] = []
                    self.music_file.save()
                    self.music_file[tag[0].upper()] = "TEST"
                    self.music_file.save()
                    self.music_file[tag[0].upper()] = val
                    self.music_file.save()
                    logging.info("%s, %s %s", tag[0], tag[0].upper(), val)
            raise TabError

    def parse_tags(self):
        if self.tag_collection.has_item(ARTIST):
            self.tag_collection.get_item(ARTIST).regex()
            self.tag_collection.get_item(ARTIST).special_recapitalize()
            self.tag_collection.get_item(ARTIST).strip()
            # uniqueArtists.add_non_standard_names(self.tag_collection.get_item(ARTIST).to_array())
        if self.tag_collection.has_item(ALBUM_ARTIST):
            self.tag_collection.get_item(ALBUM_ARTIST).regex()
            self.tag_collection.get_item(ALBUM_ARTIST).special_recapitalize()
            self.tag_collection.get_item(ALBUM_ARTIST).strip()
            # uniqueArtists.add_non_standard_names(self.tag_collection.get_item(ALBUM_ARTIST).to_array())
        if self.tag_collection.has_item(GENRE):
            self.tag_collection.get_item(GENRE).regex()
            self.tag_collection.get_item(GENRE).recapitalize()
            self.tag_collection.get_item(GENRE).strip()
            uniqueGenres.add_non_standard_names(self.tag_collection.get_item(GENRE).to_array())

    def __del__(self):
        uniqueArtists.save()
        uniqueGenres.save()
        self.save_file()

    def update_tag(self, tag, value):
        if not value:
            return
        self.tag_collection.add(tag, value)

    def delete_tag(self, tag):
        if self.music_file:
            if self.music_file.get(tag):
                self.music_file.pop(tag)
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
        if hasattr(self, 'tag_collection'):
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
                        logging.info("saving %s", self.path())
                else:
                    logging.info("Failed to save tag: %s", tag)

    def get_tag(self, tag):
        if self.music_file:
            if self.type == MusicFileType.MP3:
                return self.music_file.get(MP3Tags[tag])
            elif self.type == MusicFileType.FLAC:
                return self.music_file.get(FLACTags[tag])
            elif self.type == MusicFileType.AAC:
                return self.music_file.get(AACTags[tag])
            elif self.type == MusicFileType.WAV:
                try:
                    value = self.music_file.tags[WAVTags[tag]]
                except Exception as e:
                    logging.error(e)
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

    def set_tag(self, tag: Tag):
        logging.info("set tag %s to %s", tag.tag, tag.to_string(), self.music_file.get(tag.tag))
        if self.music_file:
            if self.type == MusicFileType.MP3:
                self.music_file[tag.tag] = tag.to_string()
            elif self.type == MusicFileType.FLAC:
                self.music_file[FLACTags[tag.tag]] = tag.to_string()
            elif self.type == MusicFileType.AAC:
                self.music_file[AACTags[tag.tag]] = tag.to_string()
            elif self.type == MusicFileType.WAV:
                # try:
                #     logging.info(self.music_file.tags[WAVTags[tag]])
                # except Exception as e:
                #     logging.info(e)
                self.music_file.tags[WAVTags[tag.tag]] = mutagen.id3.TextFrame(encoding=3, text=[tag.to_string()])
                logging.info('set %s', self.music_file.tags[WAVTags[tag.tag]])
            elif self.type == MusicFileType.M4A:
                # try:
                #     logging.info(self.music_file.tags[MP4Tags[tag]])
                # except Exception as e:
                #     logging.info(e)
                #     self.music_file.tags.add(TXXX(encoding=3, text=[tag.to_string()], desc=MP4Tags[tag]))
                self.music_file.tags[MP4Tags[tag.tag]] = str(tag.to_string())

    def analyze_track(self):
        try:
            audio_file = librosa.load(self._path)
            y, sr = audio_file
            tempo = librosa.beat.beat_track(y=y, sr=sr)
            # noinspection PyTypeChecker
            self.update_tag(BPM, str(round(tempo[0][0])))
        except Exception as e:
            if s.debug:
                logging.info('Failed to parse bpm for ' + self._path + str(e))

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
