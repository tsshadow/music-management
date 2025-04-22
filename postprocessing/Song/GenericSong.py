from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.constants import ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum

s = Settings()


class GenericSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        self._catalog_number = None
        if not self.copyright():
            if self.calculate_copyright():
                self.tag_collection.set_item(COPYRIGHT, self.calculate_copyright())
        self.get_artist_from_title()
        self.get_date_festival_from_title()
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
