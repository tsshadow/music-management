from services.common.Helpers.FilterTableHelper import FilterTableHelper
from services.common.Helpers.TableHelper import TableHelper
from services.tagger.Song.rules.TagRule import TagRule


class AddMissingGenreToDatabaseRule(TagRule):

    def __init__(self, genre_db=None, ignored_db=None, backlog_db=None):
        # pylint: disable=import-outside-toplevel
        from services.common.Helpers.Cache import databaseHelpers
        self.genre_table = genre_db or databaseHelpers.get('rules_genres') or FilterTableHelper('rules_genres', 'name', 'corrected_genre')
        self.ignored_table = ignored_db or databaseHelpers.get('rules_ignored_genres') or TableHelper('rules_ignored_genres', 'name')
        self.backlog_table = backlog_db or databaseHelpers.get('rules_genre_backlog') or TableHelper('rules_genre_backlog', 'genre')

    def apply(self, song) -> None:
        if not song.rules_genres():
            return
        for genre in song.rules_genres():
            genre = genre.strip()
            if not genre:
                continue
            if self.genre_table.exists(genre):
                continue
            if self.ignored_table.exists(genre):
                continue
            if self.backlog_table.exists(genre):
                continue

            print(f"Unknown genre '{genre}' found for {song.path()}. Adding to backlog.")
            self.backlog_table.add(genre)
