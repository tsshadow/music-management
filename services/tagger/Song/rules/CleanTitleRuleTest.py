import unittest
from unittest.mock import MagicMock
from services.tagger.Song.rules.CleanTitleRule import CleanTitleRule
from services.tagger.constants import TITLE
from services.tagger.Song.Tag import Tag

class CleanTitleRuleTest(unittest.TestCase):

    def setUp(self):
        self.song = MagicMock()
        self.title_tag = None

    def _setup_song(self, title_value):
        self.title_tag = Tag(TITLE, title_value)
        self.song.tag_collection.has_item.side_effect = lambda key: key == TITLE
        self.song.tag_collection.get_item.side_effect = lambda key: self.title_tag if key == TITLE else None
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: self.title_tag.to_string() if key == TITLE else ""

    def test_premiere(self):
        self._setup_song("Premiere: My Song")
        rule = CleanTitleRule()
        rule.apply(self.song)
        self.assertEqual(self.title_tag.to_string(), "My Song")

    def test_motz_exclusive(self):
        self._setup_song("MOTZ Exclusive: Awesome Track")
        rule = CleanTitleRule()
        rule.apply(self.song)
        self.assertEqual(self.title_tag.to_string(), "Awesome Track")

    def test_motz_premiere(self):
        self._setup_song("MOTZ Premiere: Super Hit")
        rule = CleanTitleRule()
        rule.apply(self.song)
        self.assertEqual(self.title_tag.to_string(), "Super Hit")

    def test_multiple_prefixes(self):
        self._setup_song("Premiere: MOTZ Exclusive: Multi Prefix")
        rule = CleanTitleRule()
        rule.apply(self.song)
        self.assertEqual(self.title_tag.to_string(), "Multi Prefix")

    def test_no_prefix(self):
        self._setup_song("Normal Song Title")
        rule = CleanTitleRule()
        rule.apply(self.song)
        self.assertEqual(self.title_tag.to_string(), "Normal Song Title")

    def test_prefix_middle(self):
        self._setup_song("My Premiere: Song")
        rule = CleanTitleRule()
        rule.apply(self.song)
        self.assertEqual(self.title_tag.to_string(), "My Premiere: Song")

    def test_prefix_without_space(self):
        self._setup_song("Premiere:My Song")
        rule = CleanTitleRule()
        rule.apply(self.song)
        self.assertEqual(self.title_tag.to_string(), "My Song")

if __name__ == '__main__':
    unittest.main()
