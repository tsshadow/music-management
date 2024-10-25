from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.constants import ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum

s = Settings()


class YoutubeSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        self._catalog_number = None
        paths = path.rsplit(s.delimiter, 2)
        if not self.album_artist():
            self.update_tag(ALBUM_ARTIST, str(paths[1]))
        if not self.copyright():
            self.update_tag(COPYRIGHT, self.calculate_copyright())
        self._publisher = "Youtube"
        self.update_tag(PUBLISHER, self._publisher)
        self.update_tag(CATALOG_NUMBER, self._catalog_number)
        self.get_genre_from_artist()
        self.get_genre_from_subgenres()
        self.sort_genres()
        self.parse_tags()

    def calculate_copyright(self):
        album_artist = self.album_artist()
        date = self.date()
        year = str(date)[0:4]
        if album_artist:
            if date:
                return album_artist + " (" + year + ")"
            return self.publisher()
        return None
