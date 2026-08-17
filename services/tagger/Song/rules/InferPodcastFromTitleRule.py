from services.common.Helpers.PodcastHelper import PodcastHelper
from services.tagger.constants import PODCAST, PODCAST_EPISODE, TITLE
from services.tagger.Song.rules.TagRule import TagRule

# An episode is a full mix, so the same threshold the festival rule uses to tell a
# liveset from a track applies here. It is also what keeps a split episode -- a folder
# of individual tracks -- out of the podcast browse for now.
MINIMUM_EPISODE_LENGTH = 600


class InferPodcastFromTitleRule(TagRule):
    """Infers the radio show or podcast series and episode number from the title and path."""

    def __init__(self, helper=None):
        self.podcastHelper = helper or PodcastHelper()

    def apply(self, song):
        length = song.length()
        if not length or length < MINIMUM_EPISODE_LENGTH:
            return
        # The show is named in the title for a download and in the folder for a ripped
        # series ('Podcasts/The Magic Show/2011/Podcast week 023.mp3'), so both are
        # offered to the lookup as one string.
        title = song.tag_collection.get_item_as_string(TITLE) or ''
        path = song.path() or ''
        haystack = f'{title} {path}'.strip()
        if not haystack:
            return
        info = self.podcastHelper.get(haystack)
        if not info:
            return
        song.tag_collection.set_item(PODCAST, info['podcast'])
        if info.get('episode'):
            song.tag_collection.set_item(PODCAST_EPISODE, info['episode'])
