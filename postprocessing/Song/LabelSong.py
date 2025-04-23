from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.constants import ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum

s = Settings()


class LabelSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        paths = path.rsplit(s.delimiter, 2)
        self._publisher = str(paths[0].split(s.delimiter)[-1])
        self._catalog_number = str(paths[1].split(' ')[0])
        self.tag_collection.set_item(PUBLISHER, self._publisher)
        if self._catalog_number:
            self.tag_collection.set_item(CATALOG_NUMBER, self._catalog_number)
        if not self.copyright():
            if self.calculate_copyright():
                self.tag_collection.set_item(COPYRIGHT, self.calculate_copyright())
        self.get_genre_from_label()
        self.get_genre_from_artist()
        self.get_artist_from_title()
        self.get_genre_from_subgenres()
        self.sort_genres()
        self.parse_tags()

    def calculate_copyright(self):
        publisher = self.publisher()
        date = self.date()
        year = str(date)[0:4]
        if publisher:
            if date:
                return publisher + " (" + year + ")"
            return self.publisher()
        return None
