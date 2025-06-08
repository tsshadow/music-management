import logging

from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.Song.rules.CleanAndFilterGenreRule import CleanAndFilterGenreRule
from postprocessing.Song.rules.CleanArtistFieldsRule import CleanArtistFieldsRule
from postprocessing.Song.rules.InferFestivalFromTitleRule import InferFestivalFromTitleRule
from postprocessing.Song.rules.InferGenreFromAlbumArtistRule import InferGenreFromAlbumArtistRule
from postprocessing.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from postprocessing.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from postprocessing.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from postprocessing.constants import ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum, \
    TITLE

s = Settings()


class SoundcloudSong(BaseSong):
    def __init__(self, path, extra_info=None):
        super().__init__(path, extra_info)
        paths = path.rsplit(s.delimiter, 2)
        if not self.album_artist():
            self.tag_collection.set_item(ALBUM_ARTIST, str(paths[1]))
        if not self.copyright():
            if self.calculate_copyright():
                self.tag_collection.set_item(COPYRIGHT, self.calculate_copyright())
        self._publisher = "Soundcloud"
        self.update_song(str(paths[1]))
        self.tag_collection.set_item(PUBLISHER, self._publisher)

        self.rules.append(InferRemixerFromTitleRule())
        self.rules.append(InferFestivalFromTitleRule())
        self.rules.append(InferGenreFromArtistRule())
        self.rules.append(InferGenreFromAlbumArtistRule())
        self.rules.append(InferGenreFromSubgenreRule())
        self.rules.append(CleanArtistFieldsRule())
        self.rules.append(CleanAndFilterGenreRule())
        self.run_all_rules()

    def calculate_copyright(self):
        album_artist = self.album_artist()
        date = self.date()
        year = str(date)[0:4]
        if album_artist:
            if date:
                return album_artist + " (" + year + ")"
            return self.publisher()
        return None

    def update_song(self, folder):
        ignored_artists = ['Sapher', 'C418', 'T78', 'Basher']
        if folder in ignored_artists:
            return
        if self.artist() == folder:
            if self.title().find(" @ ") != -1:
                parts = self.title().split(" @ ", 1)
                self.tag_collection.add(ARTIST, parts[0])
                self.tag_collection.set_item(TITLE, parts[1])
            elif self.title().find(" by ") != -1:
                parts = self.title().split(" by ", 1)
                self.tag_collection.add(ARTIST, parts[1])
                self.tag_collection.set_item(TITLE, parts[0])
            elif self.title().find(" - ") != -1:
                parts = self.title().split(" - ", 1)
                self.tag_collection.add(ARTIST, parts[0])
                self.tag_collection.set_item(TITLE, parts[1])
        if self.title().find(" - ") != -1:
            parts = self.title().split(" - ", 1)
            if parts[0] == self.artist():
                self.tag_collection.set_item(TITLE, parts[1])
        if self.title().find(" @ ") != -1:
            parts = self.title().split(" @ ", 1)
            if parts[0] == self.artist():
                self.tag_collection.set_item(TITLE, parts[1])

    def load_folders(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return {line.strip() for line in file if line.strip()}
        except FileNotFoundError:
            return set()  # Return an empty set if the file doesn't exist
