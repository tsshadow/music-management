from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.constants import GENRE

class CleanAndFilterGenreRule(TagRule):
    """Cleans and filters genre tag using the genre filter table."""

    def __init__(self, genre_filter_helper=None, backlog_helper=None, ignored_helper=None):
        from services.common.Helpers.FilterTableHelper import FilterTableHelper
        from services.common.Helpers.TableHelper import TableHelper
        from services.common.Helpers.Cache import databaseHelpers
        self.helper = genre_filter_helper or databaseHelpers.get('rules_genres') or FilterTableHelper('rules_genres', 'name', 'corrected_genre')
        self.backlog_helper = backlog_helper or databaseHelpers.get('rules_genre_backlog') or TableHelper('rules_genre_backlog', 'genre')
        self.ignored_helper = ignored_helper or databaseHelpers.get('rules_ignored_genres') or TableHelper('rules_ignored_genres', 'name')

    def apply(self, song, filter_genres=True):
        if not song.tag_collection.has_item(GENRE):
            return
        genre_tag = song.tag_collection.get_item(GENRE)
        genre_tag.regex()
        genre_tag.recapitalize()
        genre_tag.strip()
        genre_tag.sort()
        if filter_genres:
            rules_genres = genre_tag.to_array()
            valid_genres = []
            for genre in rules_genres:
                if self.ignored_helper.exists(genre):
                    continue
                corrected = self.helper.get_corrected_or_exists(genre)
                if isinstance(corrected, str) and corrected.strip():
                    valid_genres.append(corrected)
                elif self.backlog_helper.exists(genre):
                    valid_genres.append(genre)
            valid_genres = sorted(list(set(valid_genres)))
            if valid_genres != rules_genres:
                print(f'changed rules_genres from {rules_genres} to {valid_genres} for {song.path()}')
                genre_tag.set(valid_genres)