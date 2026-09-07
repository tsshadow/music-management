from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.Cache import databaseHelpers
from services.tagger.constants import CATALOG_NUMBER, COPYRIGHT, PUBLISHER
from services.tagger.Song import LabelPath
from services.tagger.Song.BaseSong import BaseSong
from services.tagger.Song.rules.AddMissingArtistToDatabaseRule import AddMissingArtistToDatabaseRule
from services.tagger.Song.rules.CheckArtistRule import CheckArtistRule
from services.tagger.Song.rules.CleanTagsRule import CleanTagsRule
from services.tagger.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from services.tagger.Song.rules.InferGenreFromLabelRule import InferGenreFromLabelRule
from services.tagger.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from services.tagger.Song.rules.InferReleaseDateFromNfoRule import InferReleaseDateFromNfoRule
from services.tagger.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from services.tagger.Song.rules.ReplaceInvalidUnicodeRule import ReplaceInvalidUnicodeRule
from services.tagger.Song.rules.ResolveGenreRule import ResolveGenreRule

s = Settings()


class LabelSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        publisher, release_folder = LabelPath.split(path, s.eps_folder_path, s.delimiter)
        self._publisher = str(publisher)
        self._catalog_number = str(LabelPath.catalog_number(release_folder))

    def parse(self):
        self.tag_collection.set_item(PUBLISHER, self._publisher)
        if self._catalog_number:
            self.tag_collection.set_item(CATALOG_NUMBER, self._catalog_number)
        if not self.copyright():
            c = self.calculate_copyright()
            if c:
                self.tag_collection.set_item(COPYRIGHT, c)
        self.rules.append(
            InferRemixerFromTitleRule(
                artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']
            )
        )
        self.rules.append(CleanTagsRule())
        self.rules.append(InferGenreFromArtistRule(helper=databaseHelpers['artistGenreHelper']))
        # The publisher this class just wrote from the path, read back as a genre signal.
        # This rule ran nowhere at all before: `rules_label_genre` held 49 curated rows
        # that no song type consulted, so a release on a single-genre label came out with
        # no genre whatsoever whenever its artists carried no rule of their own.
        # After the artist rule rather than before it: the artist is the more specific of
        # the two signals, and merge_and_sort keeps whatever is already there either way,
        # so the order decides which of them a reader sees first and nothing else.
        self.rules.append(InferGenreFromLabelRule(helper=databaseHelpers['labelGenreHelper']))
        self.rules.append(InferGenreFromSubgenreRule(databaseHelpers['subgenreHelper']))
        self.rules.append(CleanTagsRule())
        self.rules.append(
            AddMissingArtistToDatabaseRule(
                artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']
            )
        )
        self.rules.append(ResolveGenreRule(databaseHelpers['genre_rules']))
        self.rules.append(CleanTagsRule())
        self.rules.append(InferReleaseDateFromNfoRule(format_helper=databaseHelpers['sceneGroupDateFormatHelper']))
        self.rules.append(
            CheckArtistRule(
                artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']
            )
        )
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
