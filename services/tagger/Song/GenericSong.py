from services.common.config_store import ConfigStore as Settings
from services.common.Helpers.Cache import databaseHelpers
from services.tagger.constants import COPYRIGHT
from services.tagger.Song.BaseSong import BaseSong
from services.tagger.Song.rules.AddMissingArtistToDatabaseRule import AddMissingArtistToDatabaseRule
from services.tagger.Song.rules.CheckArtistRule import CheckArtistRule
from services.tagger.Song.rules.CleanTagsRule import CleanTagsRule
from services.tagger.Song.rules.InferFestivalFromTitleRule import InferFestivalFromTitleRule
from services.tagger.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from services.tagger.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from services.tagger.Song.rules.InferPodcastFromTitleRule import InferPodcastFromTitleRule
from services.tagger.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from services.tagger.Song.rules.ReplaceInvalidUnicodeRule import ReplaceInvalidUnicodeRule
from services.tagger.Song.rules.ResolveGenreRule import ResolveGenreRule

s = Settings()

class GenericSong(BaseSong):

    def __init__(self, path):
        super().__init__(path)
        self._catalog_number = None

    def parse(self):
        if not self.copyright() and self.calculate_copyright():
            self.tag_collection.set_item(COPYRIGHT, self.calculate_copyright())
        self.sort_genres()
        self.rules.append(InferRemixerFromTitleRule(artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']))
        # The Livesets, Podcasts and Warm Up Mixes folders all arrive here, so this is
        # where most of the actual festival recordings pass through, and the Podcasts
        # folder is the whole reason the show rule has to run here too.
        self.rules.append(InferFestivalFromTitleRule(helper=databaseHelpers['festivalHelper']))
        self.rules.append(InferPodcastFromTitleRule(helper=databaseHelpers['podcastHelper']))
        self.rules.append(CleanTagsRule())
        self.rules.append(InferGenreFromArtistRule(helper=databaseHelpers['artistGenreHelper']))
        self.rules.append(InferGenreFromSubgenreRule(databaseHelpers['subgenreHelper']))
        self.rules.append(CleanTagsRule())
        self.rules.append(AddMissingArtistToDatabaseRule(artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']))
        self.rules.append(ResolveGenreRule(databaseHelpers['genre_rules']))
        self.rules.append(CheckArtistRule(artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']))
        self.rules.append(ReplaceInvalidUnicodeRule())
        super().parse()

    def calculate_copyright(self):
        album_artist = self.album_artist()
        date = self.date()
        year = str(date)[0:4]
        if album_artist:
            if date:
                return album_artist + ' (' + year + ')'
            return self.publisher()
        return None