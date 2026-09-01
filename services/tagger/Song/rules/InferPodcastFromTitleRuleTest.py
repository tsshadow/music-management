import unittest
from unittest.mock import MagicMock

from services.tagger.constants import PODCAST, PODCAST_EPISODE
from services.tagger.Song.rules.InferPodcastFromTitleRule import InferPodcastFromTitleRule


class InferPodcastFromTitleRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.length.return_value = 3438
        self.song.path.return_value = '/mnt/music/Youtube/DJ ISAAC/HARDSTYLE SESSIONS #150.m4a'
        self.song.tag_collection.get_item_as_string.return_value = 'HARDSTYLE SESSIONS #150'
        self.tag_collection = self.song.tag_collection
        self.podcast_db = MagicMock()
        self.rule = InferPodcastFromTitleRule(helper=self.podcast_db)

    def test_sets_podcast_and_episode(self):
        self.podcast_db.get.return_value = {'podcast': "Isaac's Hardstyle Sessions", 'episode': '150'}
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_any_call(PODCAST, "Isaac's Hardstyle Sessions")
        self.tag_collection.set_item.assert_any_call(PODCAST_EPISODE, '150')

    def test_sets_only_the_show_when_no_episode_was_found(self):
        self.podcast_db.get.return_value = {'podcast': 'Q-dance Radio', 'episode': None}
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_called_once_with(PODCAST, 'Q-dance Radio')

    def test_does_nothing_if_no_match(self):
        self.podcast_db.get.return_value = None
        self.rule.apply(self.song)
        self.tag_collection.set_item.assert_not_called()

    def test_does_nothing_if_too_short(self):
        """Short files are tracks, not episodes -- the same guard festivals use."""
        self.song.length.return_value = 400
        self.rule.apply(self.song)
        self.podcast_db.get.assert_not_called()
        self.tag_collection.set_item.assert_not_called()

    def test_looks_at_the_path_as_well_as_the_title(self):
        """A show that names itself only in its folder still has to be found."""
        self.song.tag_collection.get_item_as_string.return_value = ''
        self.song.path.return_value = '/mnt/music/Podcasts/The Magic Show/2011/Podcast week 023.mp3'
        self.podcast_db.get.return_value = {'podcast': 'The Magic Show', 'episode': '023'}

        self.rule.apply(self.song)

        self.assertIn('The Magic Show', self.podcast_db.get.call_args[0][0])
        self.tag_collection.set_item.assert_any_call(PODCAST, 'The Magic Show')

    def test_skips_a_file_with_neither_title_nor_path(self):
        self.song.tag_collection.get_item_as_string.return_value = ''
        self.song.path.return_value = ''
        self.rule.apply(self.song)
        self.podcast_db.get.assert_not_called()

    def test_tolerates_an_unknown_length(self):
        """`length()` returns None for a file mutagen could not measure."""
        self.song.length.return_value = None
        self.rule.apply(self.song)
        self.podcast_db.get.assert_not_called()


if __name__ == '__main__':
    unittest.main()
