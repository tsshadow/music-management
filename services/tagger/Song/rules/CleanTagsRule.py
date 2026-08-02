from services.tagger.constants import ALBUM_ARTIST, ARTIST, GENRE, REMIXER
from services.tagger.Song.rules.TagRule import TagRule


class CleanTagsRule(TagRule):
    """Cleans artist- and genre-related tags using regex and stripping."""

    def apply(self, song):
        for field in [ARTIST, ALBUM_ARTIST, GENRE, REMIXER]:
            if song.tag_collection.has_item(field):
                tag = song.tag_collection.get_item(field)
                tag.regex()
                tag.strip()
                tag.deduplicate()