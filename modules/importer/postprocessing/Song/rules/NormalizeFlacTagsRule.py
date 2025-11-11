from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import MusicFileType


class NormalizeFlacTagsRule(TagRule):
    """Ensures all FLAC tag keys are uppercase and updates the file."""

    def apply(self, song):
        if song.type != MusicFileType.FLAC:
            return

        new_tags = {
            tag.upper(): value for tag, value in song.music_file.tags.items()
        }
        song.music_file.tags.clear()
        song.music_file.tags.update(new_tags)
        song.music_file.save()
