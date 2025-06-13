from data.settings import Settings
from postprocessing.Song.BaseSong import BaseSong
from postprocessing.Song.rules.AddMissingArtistToDatabaseRule import AddMissingArtistToDatabaseRule
from postprocessing.Song.rules.AddMissingGenreToDatabaseRule import AddMissingGenreToDatabaseRule
from postprocessing.Song.rules.CheckArtistRule import CheckArtistRule
from postprocessing.Song.rules.CleanAndFilterGenreRule import CleanAndFilterGenreRule
from postprocessing.Song.rules.CleanTagsRule import CleanTagsRule
from postprocessing.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from postprocessing.Song.rules.InferGenreFromLabelRule import InferGenreFromLabelRule
from postprocessing.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from postprocessing.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from postprocessing.constants import (
    PUBLISHER, CATALOG_NUMBER, COPYRIGHT,
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

        # self.rules.append(InferArtistFromTitleRule())       # Extract artist from title
        self.rules.append(InferRemixerFromTitleRule())  # Extract remixer info from title and add to REMIXERS
        self.rules.append(CleanTagsRule())  # Clean tags by executing regex
        self.rules.append(InferGenreFromArtistRule())  # Infer genre based on artist lookup
        self.rules.append(InferGenreFromLabelRule())  # Infer genre based on album artist lookup
        self.rules.append(InferGenreFromSubgenreRule())  # Infer genre based on subgenre mapping
        self.rules.append(CleanTagsRule())  # Re-run cleanup after inference steps
        self.rules.append(
            AddMissingArtistToDatabaseRule())  # Prompt user to classify unknown artists (valid/ignored/corrected)
        self.rules.append(
            AddMissingGenreToDatabaseRule())  # Prompt user to classify unknown artists (valid/ignored/corrected)
        self.rules.append(CleanAndFilterGenreRule())  #
        self.rules.append(CheckArtistRule())  # Normalize/correct/remove tags based on artist DB state
        self.run_all_rules()

    def calculate_copyright(self):
        publisher = self.publisher()
        date = self.date()
        if publisher:
            if date:
                return f"{publisher} ({str(date)[:4]})"
            return publisher
        return None
