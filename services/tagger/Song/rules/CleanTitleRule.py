from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.constants import TITLE

class CleanTitleRule(TagRule):
    """Removes specific prefixes from the song title."""

    def apply(self, song):
        if song.tag_collection.has_item(TITLE):
            tag = song.tag_collection.get_item(TITLE)
            title = tag.to_string()
            prefixes = ['Premiere:', 'MOTZ Exclusive:', 'MOTZ Premiere:']
            modified = False
            still_checking = True
            while still_checking:
                still_checking = False
                for prefix in prefixes:
                    if title.startswith(prefix):
                        title = title[len(prefix):].strip()
                        modified = True
                        still_checking = True
                        break
            if modified:
                tag.set(title)