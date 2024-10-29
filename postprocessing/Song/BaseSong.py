import os

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
    COPYRIGHT, ALBUM_ARTIST, BPM, MusicFileType, TITLE

s = Settings()
artistGenreHelper = LookupTableHelper('data/artist-genre.txt')
labelGenreHelper = LookupTableHelper('data/label-genre.txt')
subgenreGenreHelper = LookupTableHelper('data/subgenres-genres.txt')


class ExtensionNotSupportedException(Exception):
    pass


def custom_title(s):
    # List of words to ignore (not capitalize)
    ignore_words = {"of", "and", "the", "in", "on", "for", "with", "a", "an", "but", "to"}
    words = s.split()

    # Capitalize the first word and other words unless they are in ignore_words
    return ' '.join(
        word if word.lower() in ignore_words and i != 0 else word.title()
        for i, word in enumerate(words)
    )

class UniqueArtistHandler:
    def __init__(self, name):
        self.name = name
        self.artists = []
        self.known_artists = self.load_known_artists()
        self.known_ignored = self.load_known_ignored_artists()

    def load_known_artists(self):
        try:
            with open("data/artists.txt", "r", encoding="utf-8") as file:
                return {line.strip() for line in file if line.strip()}
        except FileNotFoundError:
            return set()

    def load_known_ignored_artists(self):
        try:
            with open("data/ignored_artists.txt", "r", encoding="utf-8") as file:
                return {line.strip() for line in file if line.strip()}
        except FileNotFoundError:
            return set()

    def add_non_standard_names(self, artists):
        non_standard = [
            artist for artist in artists
            if artist != custom_title(artist) and
               artist not in self.known_artists and
               artist not in self.known_ignored
        ]
        self.artists.extend(non_standard)

    def verify_and_save_artist(self):
        new_artists = set(self.artists) - self.known_artists - self.known_ignored
        with open("data/artists.txt", "a",  encoding="utf-8") as file:
            with open("data/ignored_artists.txt", "a",  encoding="utf-8") as ignored_file:
                for artist in sorted(new_artists):
                    response = input(f"\nIs '{artist}' correctly spelled (expected {custom_title(artist)}? (yes/no): ").strip().lower()
                    if response == "yes" or response == "y":
                        file.write(f"{artist}\n")
                        self.known_artists.add(artist)
                    elif response == "no" or  response == "n":
                        ignored_file.write(f"{artist}\n")
                        self.known_ignored.add(artist)
                    else:
                        self.artists.remove(artist)

    def save(self):
        self.verify_and_save_artist()


uniqueArtists = UniqueArtistHandler("Artists")
uniqueAlbumArtists = UniqueArtistHandler("Album Artists")


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
            ".m4a": lambda p: (MP4(p), MusicFileType.M4A)
        }
        try:
            self.music_file, self.type = music_file_classes[self._extension.lower()](path)
        except KeyError:
            raise ExtensionNotSupportedException(f"{self._extension} is not supported")
        self.tag_collection = TagCollection(self.music_file.tags)

    def parse_tags(self):
        if self.tag_collection.has_item(ARTIST):
            self.tag_collection.get_item(ARTIST).regex()
            self.tag_collection.get_item(ARTIST).special_recapitalize()
            uniqueArtists.add_non_standard_names(self.tag_collection.get_item(ARTIST).to_array())
        if self.tag_collection.has_item(ALBUM_ARTIST):
            self.tag_collection.get_item(ALBUM_ARTIST).regex()
            self.tag_collection.get_item(ALBUM_ARTIST).special_recapitalize()
            uniqueArtists.add_non_standard_names(self.tag_collection.get_item(ALBUM_ARTIST).to_array())
        if self.tag_collection.has_item(GENRE):
            self.tag_collection.get_item(GENRE).recapitalize()

    def __del__(self):
        uniqueArtists.save()
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

    def set_tag(self, tag: Tag):
        print("set tag", tag.tag, tag.to_string())
        if self.music_file:
            if self.type == MusicFileType.MP3 or self.type == MusicFileType.FLAC:
                print("was:", self.music_file.get(tag.tag))
                self.music_file[tag.tag] = tag.to_string()
            elif self.type == MusicFileType.WAV:
                try:
                    print(self.music_file.tags[WAVTags[tag]])
                except Exception as e:
                    print(e)
                    self.music_file.tags.add(TXXX(encoding=3, text=[tag.to_string()], desc=WAVTags[tag]))
                self.music_file.tags[WAVTags[tag]] = mutagen.id3.TextFrame(encoding=3, text=[tag.to_string()])
                print(' set ', self.music_file.tags[WAVTags[tag]])
            elif self.type == MusicFileType.M4A:
                self.music_file.tags[MP4Tags[tag]] = str(tag.to_string())

    def analyze_track(self):
        try:
            audio_file = librosa.load(self._path)
            y, sr = audio_file
            tempo = librosa.beat.beat_track(y=y, sr=sr)
            # noinspection PyTypeChecker
            self.update_tag(BPM, str(round(tempo[0][0])))
        except Exception as e:
            if s.debug:
                print('Failed to parse bpm for ' + self._path + str(e))

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
