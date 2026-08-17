from services.common.Helpers.FestivalHelper import FestivalHelper
from services.tagger.constants import DATE, FESTIVAL, TITLE
from services.tagger.Song.rules.TagRule import TagRule

# Below this, a file is a track and not a set. Anthems and edits carry a festival
# name in their title too, and tagging those would fill the festival lists with
# single tracks instead of the recordings you are looking for.
MIN_SET_SECONDS = 600


class InferFestivalFromTitleRule(TagRule):
    """Infers festival and date from the title, and failing that from the path."""

    def __init__(self, helper=None):
        self.festivalHelper = helper or FestivalHelper()

    def apply(self, song):
        length = song.length()
        if length and length < MIN_SET_SECONDS:
            return

        title = song.tag_collection.get_item_as_string(TITLE)
        info = self.festivalHelper.get(title) if title else None
        if not info:
            # The folder is often the better source: scene releases and rips name the
            # artist in the title and the event in the directory. A year has to be in
            # the path for this, because a bare folder name matches far too easily --
            # an artist folder called Rebelion is not the festival Rebellion.
            info = self.festivalHelper.get(song.path(), require_year=True)
        if not info:
            return

        if 'festival' in info:
            song.tag_collection.set_item(FESTIVAL, info['festival'])
        if 'date' in info:
            song.tag_collection.set_item(DATE, info['date'])
