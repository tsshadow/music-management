from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import GENRE


class CleanAndFilterGenreRule(TagRule):
    """Cleans and filters genre tag using the genre filter table."""

    def __init__(self, genre_filter_helper=None):
        from postprocessing.Song.Helpers.FilterTableHelper import FilterTableHelper
        self.helper = genre_filter_helper or FilterTableHelper("genres", "genre", "corrected_genre")

    def apply(self, song, filter_genres=True):
        if not song.tag_collection.has_item(GENRE):
            return

        genre_tag = song.tag_collection.get_item(GENRE)
        genre_tag.regex()
        genre_tag.recapitalize()
        genre_tag.strip()
        genre_tag.sort()

        if filter_genres:
            genres = genre_tag.to_array()
            valid_genres = []
            for genre in genres:
                corrected = self.helper.get_corrected_or_exists(genre)
                if isinstance(corrected, str) and corrected.strip():
                    valid_genres.append(corrected)
    
            valid_genres.sort()
            if valid_genres != genres:
                print(f'changed genres from {genres} to {valid_genres} for {song.path()}')
                genre_tag.set(valid_genres)
