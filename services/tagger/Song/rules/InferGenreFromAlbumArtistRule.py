from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.constants import GENRE, ALBUM_ARTIST
from services.common.Helpers.LookupTableHelper import LookupTableHelper

class InferGenreFromAlbumArtistRule(TagRule):
    """
    Infers rules_genres based on the album artist field.

    Uses the ALBUM_ARTIST tag to look up associated rules_genres from a label-style lookup table.
    Merges the results into the current genre tag if applicable.

    Particularly useful for compilation albums, DJ mixes, or label-driven releases where album artist reflects a curated source.
    """

    def __init__(self, helper=None):
        from services.common.Helpers.Cache import databaseHelpers
        self.labelGenreHelper = helper or databaseHelpers.get('labelGenreHelper') or LookupTableHelper('rules_label_genre', 'label', 'genre')

    def apply(self, song):
        artist = song.tag_collection.get_item_as_string(ALBUM_ARTIST)
        rules_genres = self.labelGenreHelper.get(artist)
        if rules_genres:
            current = song.tag_collection.get_item_as_array(GENRE)
            merged = song.merge_and_sort_genres(current, rules_genres)
            song.tag_collection.set_item(GENRE, ';'.join(merged))