from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import GENRE, ALBUM_ARTIST
from postprocessing.Song.Helpers.LookupTableHelper import LookupTableHelper


class InferGenreFromAlbumArtistRule(TagRule):
    """
    Infers genres based on the album artist field.

    Uses the ALBUM_ARTIST tag to look up associated genres from a label-style lookup table.
    Merges the results into the current genre tag if applicable.

    Particularly useful for compilation albums, DJ mixes, or label-driven releases where album artist reflects a curated source.
    """

    def __init__(self, helper=None):
        self.labelGenreHelper = helper or LookupTableHelper("label_genre", "label", "genre")

    def apply(self, song):
        artist = song.tag_collection.get_item_as_string(ALBUM_ARTIST)
        genres = self.labelGenreHelper.get(artist)
        if genres:
            current = song.tag_collection.get_item_as_array(GENRE)
            merged = song.merge_and_sort_genres(current, genres)
            song.tag_collection.set_item(GENRE, ";".join(merged))
