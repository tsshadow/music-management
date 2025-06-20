import logging

from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.Song.Helpers.Cache import databaseHelpers
from postprocessing.Song.rules.AddMissingArtistToDatabaseRule import AddMissingArtistToDatabaseRule
from postprocessing.Song.rules.AddMissingGenreToDatabaseRule import AddMissingGenreToDatabaseRule
from postprocessing.Song.rules.CheckArtistRule import CheckArtistRule
from postprocessing.Song.rules.CleanAndFilterGenreRule import CleanAndFilterGenreRule
from postprocessing.Song.rules.CleanTagsRule import CleanTagsRule
from postprocessing.Song.rules.InferArtistFromTitleRule import InferArtistFromTitleRule
from postprocessing.Song.rules.InferFestivalFromTitleRule import InferFestivalFromTitleRule
from postprocessing.Song.rules.InferGenreFromAlbumArtistRule import InferGenreFromAlbumArtistRule
from postprocessing.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from postprocessing.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from postprocessing.Song.rules.InferGenreFromTitleRule import InferGenreFromTitleRule
from postprocessing.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from postprocessing.Song.rules.MergeDrumAndBassGenresRule import MergeDrumAndBassGenresRule
from postprocessing.constants import ALBUM_ARTIST, PUBLISHER, CATALOG_NUMBER, GENRE, ARTIST, COPYRIGHT, FormatEnum, \
    TITLE

s = Settings()


class SoundcloudSong(BaseSong):
    def __init__(self, path, extra_info=None):
        super().__init__(path, extra_info)
        paths = path.rsplit(s.delimiter, 2)
        if not self.album_artist():
            self.tag_collection.set_item(ALBUM_ARTIST, str(paths[1]))
        if not self.copyright():
            if self.calculate_copyright():
                self.tag_collection.set_item(COPYRIGHT, self.calculate_copyright())
        self._publisher = "Soundcloud"
        self.tag_collection.set_item(PUBLISHER, self._publisher)
        # Rules voor tag-inferentie en opschoning
        self.rules.append(InferArtistFromTitleRule(
            artist_db=databaseHelpers["artists"],
            ignored_db=databaseHelpers["ignored_artists"],
            genre_db=databaseHelpers["genres"]
        ))       # Extract artist from title
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
        ))  # Clean/correct genre tags based on DB

        self.rules.append(CleanTagsRule())  # Re-run cleanup after inference steps

        self.rules.append(CheckArtistRule(
            artist_db=databaseHelpers["artists"],
            ignored_db=databaseHelpers["ignored_artists"]
        ))  # Normalize/correct/remove tags based on artist DB state

        self.run_all_rules()


    def calculate_copyright(self):
        album_artist = self.album_artist()
        date = self.date()
        year = str(date)[0:4]
        if album_artist:
            if date:
                return album_artist + " (" + year + ")"
            return self.publisher()
        return None


    def load_folders(self, file_path):
        try:
            with open(file_path, "r", encoding="utf-8") as file:
                return {line.strip() for line in file if line.strip()}
        except FileNotFoundError:
            return set()  # Return an empty set if the file doesn't exist
