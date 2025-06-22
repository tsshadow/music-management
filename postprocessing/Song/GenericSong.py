from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.Song.Helpers.Cache import databaseHelpers
from postprocessing.Song.rules.AddMissingArtistToDatabaseRule import AddMissingArtistToDatabaseRule
from postprocessing.Song.rules.AddMissingGenreToDatabaseRule import AddMissingGenreToDatabaseRule
from postprocessing.Song.rules.CheckArtistRule import CheckArtistRule
from postprocessing.Song.rules.CleanAndFilterGenreRule import CleanAndFilterGenreRule
from postprocessing.Song.rules.CleanTagsRule import CleanTagsRule
from postprocessing.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from postprocessing.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from postprocessing.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from postprocessing.constants import ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum

s = Settings()


class GenericSong(BaseSong):
    def __init__(self, path):
        super().__init__(path)
        self._catalog_number = None

    def parse(self):
        if not self.copyright():
            if self.calculate_copyright():
                self.tag_collection.set_item(COPYRIGHT, self.calculate_copyright())
        self.sort_genres()

        self.rules.append(InferRemixerFromTitleRule(
            artist_db=databaseHelpers["artists"],
            ignored_db=databaseHelpers["ignored_artists"]
        ))  # Extract remixer info from title and add to REMIXERS

        self.rules.append(CleanTagsRule())  # Clean tags by executing regex

        self.rules.append(InferGenreFromArtistRule(
            helper=databaseHelpers["artistGenreHelper"]
        ))  # Infer genre based on artist lookup

        self.rules.append(InferGenreFromSubgenreRule(
            databaseHelpers["subgenreHelper"]
        ))  # Infer genre based on subgenre mapping

        self.rules.append(CleanTagsRule())  # Re-run cleanup after inference steps

        self.rules.append(AddMissingArtistToDatabaseRule(
            artist_db=databaseHelpers["artists"],
            ignored_db=databaseHelpers["ignored_artists"]
        ))  # Prompt user to classify unknown artists (valid/ignored/corrected)

        self.rules.append(AddMissingGenreToDatabaseRule(
            genre_db=databaseHelpers["genres"],
            ignored_db=databaseHelpers["ignored_genres"]
        ))  # Prompt user to classify unknown genres (valid/ignored/corrected)

        self.rules.append(CleanAndFilterGenreRule(
            databaseHelpers["genres"]
        ))

        self.rules.append(CheckArtistRule(
            artist_db=databaseHelpers["artists"],
            ignored_db=databaseHelpers["ignored_artists"]
        ))  # Normalize/correct/remove tags based on artist DB state

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
