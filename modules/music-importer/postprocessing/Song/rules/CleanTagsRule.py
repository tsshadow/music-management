from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import ARTIST, ALBUM_ARTIST, GENRE, REMIXER


class CleanTagsRule(TagRule):
    """Cleans artist- and genre-related tags using regex and stripping."""

    def apply(self, song):
        for field in [ARTIST, ALBUM_ARTIST, GENRE, REMIXER]:
            if song.tag_collection.has_item(field):
                tag = song.tag_collection.get_item(field)
                tag.regex()
                tag.strip()
                tag.deduplicate()
