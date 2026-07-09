from services.tagger.Song.rules.TagRule import TagRule
from services.tagger.constants import MusicFileType

class NormalizeFlacTagsRule(TagRule):
    """Ensures all FLAC tag keys are uppercase and updates the file."""

    def apply(self, song):
        if song.type != MusicFileType.FLAC:
            return
        
        tags = song.music_file.tags
        if tags is None:
            return

        new_tags = {tag.upper(): value for tag, value in tags.items()}
        
        # Check if anything actually changed (keys or values)
        if new_tags != dict(tags):
            tags.clear()
            tags.update(new_tags)
            song.music_file.save()
