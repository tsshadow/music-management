from services.tagger.Song.SongHelper import merge_and_sort_genres
from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.constants import ARTIST, GENRE
from services.common.Helpers.LookupTableHelper import LookupTableHelper

class InferGenreFromArtistRule(TagRule):
    """
    Infers rules_genres based on the song's listed artist(s).

    This rule looks up each artist from the ARTIST tag in a known artist→genre mapping.
    Any rules_genres found are merged with the current genre tag, avoiding duplicates and preserving order.

    Useful when the artist is a strong indicator of the genre, especially for known solo acts or DJs.
    """

    def __init__(self, helper=None):
        # pylint: disable=import-outside-toplevel
        from services.common.Helpers.Cache import databaseHelpers
        self.artistGenreHelper = helper or databaseHelpers.get('artistGenreHelper') or LookupTableHelper('rules_artist_genre', 'artist', 'genre')

    def apply(self, song):
        current_genres = song.tag_collection.get_item_as_array(GENRE)
        for artist in song.tag_collection.get_item_as_array(ARTIST):
            rules_genres = self.artistGenreHelper.get(str(artist))
            if rules_genres:
                current_genres = merge_and_sort_genres(current_genres, rules_genres)
        song.tag_collection.set_item(GENRE, ';'.join(current_genres))
