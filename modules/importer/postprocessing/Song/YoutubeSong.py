from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.Song.rules.CleanAndFilterGenreRule import CleanAndFilterGenreRule
from postprocessing.Song.rules.CleanTagsRule import CleanTagsRule
from postprocessing.Song.rules.InferFestivalFromTitleRule import InferFestivalFromTitleRule
from postprocessing.Song.rules.InferGenreFromAlbumArtistRule import InferGenreFromAlbumArtistRule
from postprocessing.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from postprocessing.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from postprocessing.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from postprocessing.Song.rules.ReplaceInvalidUnicodeRule import ReplaceInvalidUnicodeRule
from postprocessing.constants import ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum, \
    TITLE, ALBUM

s = Settings()


class YoutubeSong(BaseSong):
    def __init__(self, path, extra_info=None):
        super().__init__(path, extra_info)
        self._catalog_number = None
        paths = path.rsplit(s.delimiter, 2)
        self._album_artist_from_path = str(paths[1])
        self._publisher = "Youtube"
        channel = None
        if extra_info:
            channel = (
                extra_info.get("uploader")
                or extra_info.get("channel")
                or extra_info.get("uploader_id")
                or extra_info.get("channel_id")
            )
        self._channel_for_album = channel or self._album_artist_from_path
        self._album = f"{self._publisher} ({self._channel_for_album})"

    def parse(self):
        if not self.album_artist():
            self.tag_collection.set_item(ALBUM_ARTIST, self._album_artist_from_path)
        if not self.album():
            self.tag_collection.set_item(ALBUM, self._album)
        if not self.copyright():
            if self.calculate_copyright():
                self.tag_collection.set_item(COPYRIGHT, self.calculate_copyright())
        self.update_song(self._album_artist_from_path)
        self.tag_collection.set_item(PUBLISHER, self._publisher)
        if self._catalog_number:
            self.tag_collection.set_item(CATALOG_NUMBER, self._catalog_number)

        self.rules.append(InferRemixerFromTitleRule())
        self.rules.append(InferFestivalFromTitleRule())
        self.rules.append(InferGenreFromArtistRule())
        self.rules.append(InferGenreFromAlbumArtistRule())
        self.rules.append(InferGenreFromSubgenreRule())
        self.rules.append(CleanTagsRule())
        self.rules.append(CleanAndFilterGenreRule())
        self.rules.append(ReplaceInvalidUnicodeRule())
        super().parse()

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
        ignored_artists = []
        if folder in ignored_artists:
            return
        if self.artist() == self.album_artist() and self.artist() == folder:
            if self.title().find(" - ") != -1:
                parts = self.title().split(" - ", 1)
                self.tag_collection.add(ARTIST, parts[0])
                self.tag_collection.set_item(TITLE, parts[1])
            if self.title().find(" @ ") != -1:
                parts = self.title().split(" @ ", 1)
                self.tag_collection.add(ARTIST, parts[1])
                self.tag_collection.set_item(TITLE, parts[0])

    def load_folders(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return {line.strip() for line in file if line.strip()}
        except FileNotFoundError:
            return set()  # Return an empty set if the file doesn't exist
