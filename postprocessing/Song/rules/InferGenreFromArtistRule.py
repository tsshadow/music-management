from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import ARTIST, GENRE
from postprocessing.Song.Helpers.LookupTableHelper import LookupTableHelper

class InferGenreFromArtistRule(TagRule):
    """
    Infers genres based on the song's listed artist(s).

    This rule looks up each artist from the ARTIST tag in a known artist→genre mapping.
    Any genres found are merged with the current genre tag, avoiding duplicates and preserving order.

    Useful when the artist is a strong indicator of the genre, especially for known solo acts or DJs.
    """

    def __init__(self, helper=None):
        self.artistGenreHelper = helper or LookupTableHelper("artist_genre", "artist", "genre")

    def apply(self, song):
        current_genres = song.tag_collection.get_item_as_array(GENRE)

        for artist in song.tag_collection.get_item_as_array(ARTIST):
            genres = self.artistGenreHelper.get(str(artist))
            print(genres, artist)
            if genres:
                current_genres = song.merge_and_sort_genres(current_genres, genres)

        song.tag_collection.set_item(GENRE, ";".join(current_genres))
