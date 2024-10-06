from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.constants import ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum

s = Settings()


class LabelBaseSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        paths = path.rsplit(s.delimiter, 2)
        self._publisher = str(paths[0].split(s.delimiter)[-1])
        self._catalog_number = str(paths[1].split(' ')[0])
        self.check_or_update_tag(ALBUM_ARTIST, self.parse_artist(self.album_artist()))
        self.check_or_update_tag(PUBLISHER, self._publisher)
        self.check_or_update_tag(CATALOG_NUMBER, self._catalog_number)
        self.check_or_update_tag(GENRE, self.genre(FormatEnum.RECAPITALIZE))
        self.check_or_update_tag(ARTIST, self.parse_artist(self.artist()))
        self.check_or_update_tag(COPYRIGHT, self.calculate_copyright())

    def calculate_copyright(self):
        publisher = self.publisher()
        date = self.date()
        year = str(date)[0:4]
        if publisher:
            if date:
                return publisher + " (" + year + ")"
            return self.publisher()
        return None
