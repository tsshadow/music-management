import unittest
from unittest.mock import MagicMock, call
from postprocessing.Song.rules.InferGenreFromTitleRule import InferGenreFromTitleRule
from postprocessing.constants import TITLE, GENRE


class InferGenreFromTitleRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.path.return_value = "/path/to/song.mp3"
        self.song.tag_collection.get_item_as_string.return_value = "This is a Hardstyle Anthem"

        self.genre_table = MagicMock()
        self.genre_table.get_all_values.return_value = ["Hardstyle", "Techno", "House"]
        self.genre_table.get.side_effect = lambda g: g.capitalize()

        self.rule = InferGenreFromTitleRule(genre_db=self.genre_table, dryrun=False)

    def test_detects_genre_in_title(self):
        result = self.rule.apply(self.song)

        self.assertTrue(result)
        self.song.tag_collection.add.assert_called_once_with(GENRE, "Hardstyle")

    def test_does_not_trigger_on_unmatched_title(self):
        self.song.tag_collection.get_item_as_string.return_value = "Some random title without genre"
        result = self.rule.apply(self.song)

        self.assertFalse(result)
        self.song.tag_collection.add.assert_not_called()

    def test_detects_multiple_genres(self):
        self.song.tag_collection.get_item_as_string.return_value = "Hardstyle meets House in the new track"
        result = self.rule.apply(self.song)

        self.assertTrue(result)
        self.song.tag_collection.add.assert_has_calls([
            call(GENRE, "Hardstyle"),
            call(GENRE, "House"),
        ], any_order=True)
        self.assertEqual(self.song.tag_collection.add.call_count, 2)

    def test_skips_empty_title(self):
        self.song.tag_collection.get_item_as_string.return_value = ""
        result = self.rule.apply(self.song)

        self.assertFalse(result)
        self.song.tag_collection.add.assert_not_called()


if __name__ == "__main__":
    unittest.main()
