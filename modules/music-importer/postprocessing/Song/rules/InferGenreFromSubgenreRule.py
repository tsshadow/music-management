from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import GENRE
from postprocessing.Song.Helpers.LookupTableHelper import LookupTableHelper


class InferGenreFromSubgenreRule(TagRule):
    """
    Infers broader genres based on subgenres using a lookup table.

    For example, if a song has the subgenre 'Uptempo Hardcore' or 'Mainstream Hardcore',
    this rule adds 'Hardcore' to the genre tag to ensure consistent genre grouping.
    """

    def __init__(self, helper=None):
        self.subgenreHelper = helper or LookupTableHelper("subgenre_genre", "subgenre", "genre")

    def apply(self, song):
        current_genres = song.tag_collection.get_item_as_array(GENRE)
        new_genres = set(current_genres)

        for genre in current_genres:
            broader = self.subgenreHelper.get(genre)
            if broader:
                new_genres.update(broader)

        merged = song.merge_and_sort_genres(current_genres, list(new_genres))
        song.tag_collection.set_item(GENRE, ";".join(merged))
