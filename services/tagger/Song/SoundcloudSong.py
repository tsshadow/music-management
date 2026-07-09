from services.common.settings import Settings
from services.tagger.Song.BaseSong import BaseSong
from services.common.Helpers.Cache import databaseHelpers
from services.tagger.Song.rules.AddMissingArtistToDatabaseRule import AddMissingArtistToDatabaseRule
from services.tagger.Song.rules.AddMissingGenreToDatabaseRule import AddMissingGenreToDatabaseRule
from services.tagger.Song.rules.CheckArtistRule import CheckArtistRule
from services.tagger.Song.rules.CleanAndFilterGenreRule import CleanAndFilterGenreRule
from services.tagger.Song.rules.CleanTagsRule import CleanTagsRule
from services.tagger.Song.rules.CleanTitleRule import CleanTitleRule
from services.tagger.Song.rules.InferArtistFromTitleRule import InferArtistFromTitleRule
from services.tagger.Song.rules.InferFeatureFromTitleRule import InferFeatureFromTitleRule
from services.tagger.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from services.tagger.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from services.tagger.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from services.tagger.Song.rules.ReplaceInvalidUnicodeRule import ReplaceInvalidUnicodeRule
from services.tagger.constants import ALBUM_ARTIST, PUBLISHER, COPYRIGHT, ALBUM, ARTIST
s = Settings()

class SoundcloudSong(BaseSong):

    def __init__(self, path, extra_info=None):
        super().__init__(path, extra_info)
        paths = path.rsplit(s.delimiter, 2)
        self._album_artist_from_path = str(paths[1])
        self._publisher = 'Soundcloud'
        uploader = None
        if extra_info:
            uploader = extra_info.get('uploader')
        self._uploader = uploader or self._album_artist_from_path
        self._album = f'{self._publisher} ({self._uploader})'

    def parse(self):
        if not self.album_artist():
            self.tag_collection.set_item(ALBUM_ARTIST, self._album_artist_from_path)
        if not self.artist():
            self.tag_collection.set_item(ARTIST, self._uploader)
        if not self.album():
            self.tag_collection.set_item(ALBUM, self._album)
        if not self.copyright():
            if self.calculate_copyright():
                self.tag_collection.set_item(COPYRIGHT, self.calculate_copyright())
        self.tag_collection.set_item(PUBLISHER, self._publisher)
        self.rules.append(CleanTitleRule())
        self.rules.append(InferArtistFromTitleRule(artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists'], genre_db=databaseHelpers['rules_genres']))
        self.rules.append(InferRemixerFromTitleRule(artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']))
        self.rules.append(InferFeatureFromTitleRule())
        self.rules.append(CleanTagsRule())
        self.rules.append(InferGenreFromArtistRule(helper=databaseHelpers['artistGenreHelper']))
        self.rules.append(InferGenreFromSubgenreRule(databaseHelpers['subgenreHelper']))
        self.rules.append(CleanTagsRule())
        self.rules.append(AddMissingArtistToDatabaseRule(artist_db=databaseHelpers['library_artists'], ignored_db=databaseHelpers['rules_ignored_artists']))
        self.rules.append(AddMissingGenreToDatabaseRule(genre_db=databaseHelpers['rules_genres'], ignored_db=databaseHelpers['rules_ignored_genres'], backlog_db=databaseHelpers.get('rules_genre_backlog')))
        self.rules.append(CleanAndFilterGenreRule(databaseHelpers['rules_genres'], databaseHelpers.get('rules_genre_backlog'), databaseHelpers.get('rules_ignored_genres')))
        self.rules.append(CleanTagsRule())
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

    def load_folders(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return {line.strip() for line in file if line.strip()}
        except FileNotFoundError:
            return set()