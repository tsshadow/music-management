from collections import Counter

from services.tagger.constants import ORIGINAL_ARTIST, ORIGINAL_TITLE, TITLE
from services.tagger.Song.rules.TagRule import TagRule

#: Tags that hold one value by definition, and which the defect below multiplied.
SINGLE_VALUE_TAGS = (ORIGINAL_TITLE, TITLE, ORIGINAL_ARTIST)


class CollapseRepeatedValuesRule(TagRule):
    """Collapses a title or credit that an old m4a defect repeated into a single value again.

    Until 0.72.2 the tagger wrote ORIGINAL_TITLE to a bare `ORIGINAL_TITLE` key, which mutagen
    stores as a 4-byte `ORIG` atom; reading back yields `ORIG`, so the next save wrote a second
    `ORIG` atom beside the first, and mutagen merges same-named atoms into one list on read. Each
    retag added one more copy, and the title the artist rules derive from ORIGINAL_TITLE grew
    with it: production files carried `Until It's Gone` 241 times over, 3,800 characters, which
    no longer fit library_tracks.title (bug report 117). The truncation is fixed; the copies
    already on disk are what this undoes.

    Only a tag whose values actually repeat is touched -- that is the signature of the defect.
    A title that legitimately contains ';' splits into distinct values and is left alone.
    ORIGINAL_TITLE keeps its longest value: the downloaded title, which every value derived
    from it is a part of. TITLE and ORIGINAL_ARTIST keep their most frequent value, the one the
    rules produced pass after pass; the artist rules that run next re-derive TITLE from the
    repaired ORIGINAL_TITLE anyway whenever one of them matches.
    """

    def apply(self, song):
        collection = song.tag_collection
        for key in SINGLE_VALUE_TAGS:
            if not collection.has_item(key):
                continue
            values = [value for value in collection.get_item_as_array(key) if value]
            if len(values) == len(set(values)):
                continue
            collection.set_item(key, self._keep(key, values))

    @staticmethod
    def _keep(key, values):
        """The one value a repeated tag collapses to: longest for ORIGINAL_TITLE, else most frequent."""
        if key == ORIGINAL_TITLE:
            return max(values, key=len)
        return Counter(values).most_common(1)[0][0]
