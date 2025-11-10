from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import PUBLISHER, GENRE
from postprocessing.Song.Helpers.LookupTableHelper import LookupTableHelper


class InferGenreFromLabelRule(TagRule):
    """
    Infers genres based on the song's publisher (label).

    This rule retrieves the label from the PUBLISHER tag and looks up associated genres.
    These are merged into the song's genre list if not already present.

    Ideal for enriching genre metadata when a label has a consistent genre style or brand identity.
    """

    def __init__(self, helper=None):
        self.labelGenreHelper = helper or LookupTableHelper("label_genre", "label", "genre")

    def apply(self, song):
        publisher = song.tag_collection.get_item_as_string(PUBLISHER)
        genres = self.labelGenreHelper.get(publisher)
        if genres:
            current_genres = song.tag_collection.get_item_as_array(GENRE)
            merged = song.merge_and_sort_genres(current_genres, genres)
            song.tag_collection.set_item(GENRE, ";".join(merged))
