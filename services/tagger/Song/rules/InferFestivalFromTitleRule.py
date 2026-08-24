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
        matches = self.festivalHelper.get_all(title) if title else []
        if not matches:
            # The folder is often the better source: scene releases and rips name the
            # artist in the title and the event in the directory. A year has to be in
            # the path for this, because a bare folder name matches far too easily --
            # an artist folder called Rebelion is not the festival Rebellion.
            matches = self.festivalHelper.get_all(song.path(), require_year=True)
        if not matches:
            return

        # A set can belong to two events at once -- a Flashback set played at Reverze --
        # and both names belong on the file, the way two genres do. Sorted, because the
        # order the helper found them in is not meaningful and an unstable order would
        # rewrite the file on every pass.
        names = sorted({match['festival'] for match in matches if match.get('festival')})
        if names:
            song.tag_collection.set_item(FESTIVAL, ';'.join(names))
        # The date can only describe one edition, so it comes from the most specific
        # match that knows one.
        date = next((match['date'] for match in matches if 'date' in match), None)
        if date:
            song.tag_collection.set_item(DATE, date)
