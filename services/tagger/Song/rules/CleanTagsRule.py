from services.tagger.constants import ALBUM_ARTIST, ARTIST, GENRE, ORIGINAL_ARTIST, REMIXER
from services.tagger.Song.rules.TagRule import TagRule


class CleanTagsRule(TagRule):
    """Cleans artist- and genre-related tags using regex and stripping."""

    def apply(self, song):
        for field in [ARTIST, ALBUM_ARTIST, GENRE, REMIXER]:
            if song.tag_collection.has_item(field):
                tag = song.tag_collection.get_item(field)
                original = tag.to_string() if field == ARTIST else None
                tag.regex()
                tag.strip()
                tag.deduplicate()
                # Only the first pass over a file's own artist string ever has anything to
                # capture: the regex split is what discards "feat"/"vs"/"&", and once it has
                # run once (this pass, or a prior tag write already on disk) there is nothing
                # left to preserve. has_item guards against a later retag clobbering a value
                # captured on an earlier one, the same way InferArtistFromTitleRule guards
                # ORIGINAL_TITLE.
                if (
                    field == ARTIST
                    and original
                    and tag.to_string() != original
                    and not song.tag_collection.has_item(ORIGINAL_ARTIST)
                ):
                    song.tag_collection.set_item(ORIGINAL_ARTIST, original)
