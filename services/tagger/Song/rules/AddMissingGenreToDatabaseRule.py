from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.common.Helpers.TableHelper import TableHelper
from services.tagger.Song.rules.TagRule import TagRule


class AddMissingGenreToDatabaseRule(TagRule):

    def __init__(self, genre_db=None, ignored_db=None):
        self.genre_table = genre_db or TableHelper('genres', 'genre')
        self.ignored_table = ignored_db or FilterTableHelper('ignored_genres', 'name', 'corrected_name')

    def apply(self, song) -> None:
        if not song.genres():
            return
        for genre in song.genres():
            genre = genre.strip()
            if not genre:
                continue
            if self.genre_table.exists(genre):
                continue
            if self.ignored_table.exists(genre):
                continue