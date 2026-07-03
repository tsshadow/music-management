from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.constants import PUBLISHER, GENRE
from services.common.Helpers.LookupTableHelper import LookupTableHelper

class InferGenreFromLabelRule(TagRule):
    """
    Infers rules_genres based on the song's publisher (label).

    This rule retrieves the label from the PUBLISHER tag and looks up associated rules_genres.
    These are merged into the song's genre list if not already present.

    Ideal for enriching genre metadata when a label has a consistent genre style or brand identity.
    """

    def __init__(self, helper=None):
        self.labelGenreHelper = helper or LookupTableHelper('rules_label_genre', 'label', 'genre')

    def apply(self, song):
        publisher = song.tag_collection.get_item_as_string(PUBLISHER)
        rules_genres = self.labelGenreHelper.get(publisher)
        if rules_genres:
            current_genres = song.tag_collection.get_item_as_array(GENRE)
            merged = song.merge_and_sort_genres(current_genres, rules_genres)
            song.tag_collection.set_item(GENRE, ';'.join(merged))