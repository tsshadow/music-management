from services.common.settings import Settings
from services.tagger.Song.BaseSong import BaseSong
from services.common.Helpers.Cache import databaseHelpers
from services.tagger.Song.rules.AddMissingArtistToDatabaseRule import AddMissingArtistToDatabaseRule
from services.tagger.Song.rules.AddMissingGenreToDatabaseRule import AddMissingGenreToDatabaseRule
from services.tagger.Song.rules.CheckArtistRule import CheckArtistRule
from services.tagger.Song.rules.CleanAndFilterGenreRule import CleanAndFilterGenreRule
from services.tagger.Song.rules.CleanTagsRule import CleanTagsRule
from services.tagger.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from services.tagger.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from services.tagger.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from services.tagger.Song.rules.ReplaceInvalidUnicodeRule import ReplaceInvalidUnicodeRule
from services.tagger.constants import PUBLISHER, CATALOG_NUMBER, COPYRIGHT
s = Settings()

class LabelSong(BaseSong):

    def __init__(self, path):
        super().__init__(path)
        paths = path.rsplit(s.delimiter, 2)
        self._publisher = str(paths[0].split(s.delimiter)[-1])
        self._catalog_number = str(paths[1].split(' ')[0])

    def parse(self):
        self.tag_collection.set_item(PUBLISHER, self._publisher)
        if self._catalog_number:
            self.tag_collection.set_item(CATALOG_NUMBER, self._catalog_number)
        if not self.copyright():
            c = self.calculate_copyright()
            if c:
                self.tag_collection.set_item(COPYRIGHT, c)
        self.rules.append(InferRemixerFromTitleRule(artist_db=databaseHelpers['artists'], ignored_db=databaseHelpers['ignored_artists']))
        self.rules.append(CleanTagsRule())
        self.rules.append(InferGenreFromArtistRule(helper=databaseHelpers['artistGenreHelper']))
        self.rules.append(InferGenreFromSubgenreRule(databaseHelpers['subgenreHelper']))
        self.rules.append(CleanTagsRule())
        self.rules.append(AddMissingArtistToDatabaseRule(artist_db=databaseHelpers['artists'], ignored_db=databaseHelpers['ignored_artists']))
        self.rules.append(AddMissingGenreToDatabaseRule(genre_db=databaseHelpers['genres'], ignored_db=databaseHelpers['ignored_genres']))
        self.rules.append(CleanAndFilterGenreRule(databaseHelpers['genres']))
        self.rules.append(CleanTagsRule())
        self.rules.append(CheckArtistRule(artist_db=databaseHelpers['artists'], ignored_db=databaseHelpers['ignored_artists']))
        self.rules.append(ReplaceInvalidUnicodeRule())
        super().parse()

    def calculate_copyright(self):
        publisher = self.publisher()
        date = self.date()
        if publisher:
            if date:
                return f'{publisher} ({str(date)[:4]})'
            return publisher
        return None