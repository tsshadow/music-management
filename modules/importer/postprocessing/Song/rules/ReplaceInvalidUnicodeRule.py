from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import ARTIST, ALBUM_ARTIST, GENRE


class ReplaceInvalidUnicodeRule(TagRule):
    """Replace undesirable zero-width characters with semicolons."""

    def __init__(self, invalid_chars=None):
        self.invalid_chars = invalid_chars or ['\ufeff']

    def apply(self, song):
        for field in [ARTIST, ALBUM_ARTIST, GENRE]:
            if song.tag_collection.has_item(field):
                tag = song.tag_collection.get_item(field)
                value = tag.to_string()
                new_value = value
                for char in self.invalid_chars:
                    if char in new_value:
                        new_value = new_value.replace(char, ';')
                if new_value != value:
                    tag.set(new_value)
                    tag.deduplicate()
