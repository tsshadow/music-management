from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import ARTIST, ALBUM_ARTIST


class CleanArtistFieldsRule(TagRule):
    """Cleans artist-related tags using regex, capitalization, and stripping."""

    def apply(self, song):
        for field in [ARTIST, ALBUM_ARTIST]:
            if song.tag_collection.has_item(field):
                tag = song.tag_collection.get_item(field)
                tag.regex()
                tag.special_recapitalize()
                tag.strip()