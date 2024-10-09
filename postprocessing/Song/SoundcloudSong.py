from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.constants import ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum

s = Settings()


class SoundcloudSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        self._catalog_number = None
        paths = path.rsplit(s.delimiter, 2)
        self.check_or_update_tag(ALBUM_ARTIST, str(paths[1]))
        self._publisher = "Soundcloud"
        self.check_or_update_tag(PUBLISHER, self._publisher)
        self.check_or_update_tag(CATALOG_NUMBER, self._catalog_number)
        self.check_or_update_tag(GENRE, self.genre(FormatEnum.RECAPITALIZE))
        self.check_or_update_tag(ARTIST, self.parse_artist(self.artist()))
        self.check_or_update_tag(COPYRIGHT, self.calculate_copyright())
        self.get_genre_from_artist()
        self.get_genre_from_subgenres()
        self.sort_genres()
        self.save_file()

    def calculate_copyright(self):
        album_artist = self.album_artist()
        date = self.date()
        year = str(date)[0:4]
        if album_artist:
            if date:
                return album_artist + " (" + year + ")"
            return self.publisher()
        return None
