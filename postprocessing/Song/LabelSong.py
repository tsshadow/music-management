from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.Song.rules.CleanAndFilterGenreRule import CleanAndFilterGenreRule
from postprocessing.Song.rules.CleanArtistFieldsRule import CleanArtistFieldsRule
from postprocessing.Song.rules.CleanArtistFieldsRuleTest import CleanArtistFieldsRuleTest
from postprocessing.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from postprocessing.Song.rules.InferGenreFromLabelRule import InferGenreFromLabelRule
from postprocessing.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from postprocessing.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from postprocessing.constants import (
    ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum
)

s = Settings()


class LabelSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        paths = path.rsplit(s.delimiter, 2)
        self._publisher = str(paths[0].split(s.delimiter)[-1])
        self._catalog_number = str(paths[1].split(" ")[0])

        self.tag_collection.set_item(PUBLISHER, self._publisher)
        if self._catalog_number:
            self.tag_collection.set_item(CATALOG_NUMBER, self._catalog_number)

        if not self.copyright():
            c = self.calculate_copyright()
            if c:
                self.tag_collection.set_item(COPYRIGHT, c)

        self.rules.append(InferGenreFromLabelRule())
        self.rules.append(InferGenreFromArtistRule())
        self.rules.append(InferRemixerFromTitleRule())
        self.rules.append(InferGenreFromSubgenreRule())
        self.rules.append(CleanArtistFieldsRule())
        self.rules.append(CleanAndFilterGenreRule())
        self.run_all_rules()

    def calculate_copyright(self):
        publisher = self.publisher()
        date = self.date()
        if publisher:
            if date:
                return f"{publisher} ({str(date)[:4]})"
            return publisher
        return None
