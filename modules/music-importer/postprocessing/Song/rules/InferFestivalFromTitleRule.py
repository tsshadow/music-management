from postprocessing.Song.Helpers.FestivalHelper import FestivalHelper
from postprocessing.Song.rules.TagRule import TagRule
from postprocessing.constants import TITLE, FESTIVAL, DATE


class InferFestivalFromTitleRule(TagRule):
    """Infers festival and date from the title using fuzzy title lookup in festival_db."""

    def __init__(self, helper=None):
        self.festivalHelper = helper or FestivalHelper()

    def apply(self, song):
        title = song.tag_collection.get_item_as_string(TITLE)
        if not title or (song.length() and song.length() < 600):
            return

        info = self.festivalHelper.get(title)
        if not info:
            return

        if "festival" in info:
            song.tag_collection.set_item(FESTIVAL, info["festival"])

        if "date" in info:
            song.tag_collection.set_item(DATE, info["date"])
