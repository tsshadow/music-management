# tests/rules/test_infer_genre_from_label_rule.py

import unittest
from unittest.mock import MagicMock

from postprocessing.Song.rules.InferGenreFromLabelRule import InferGenreFromLabelRule
from postprocessing.constants import GENRE, PUBLISHER


class InferGenreFromLabelRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.merge_and_sort_genres = lambda a, b: sorted(set(a + b))
        self.song.tag_collection.set_item = MagicMock()

    def test_does_not_duplicate_existing_genre(self):
        """Publisher returns genre that already exists."""
        self.song.tag_collection.get_item_as_string = MagicMock(return_value="Q-Dance")
        self.song.tag_collection.get_item_as_array = MagicMock(return_value=["Hardstyle"])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Hardstyle"])

        rule = InferGenreFromLabelRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Hardstyle")

    def test_adds_new_genre(self):
        """Publisher returns genre not in current tags."""
        self.song.tag_collection.get_item_as_string = MagicMock(return_value="Thunderdome")
        self.song.tag_collection.get_item_as_array = MagicMock(return_value=["Hardcore"])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Gabber"])

        rule = InferGenreFromLabelRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Gabber;Hardcore")

    def test_sets_genre_when_none_exist(self):
        """Publisher returns genre when no genres are tagged yet."""
        self.song.tag_collection.get_item_as_string = MagicMock(return_value="MOH")
        self.song.tag_collection.get_item_as_array = MagicMock(return_value=[])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Uptempo"])

        rule = InferGenreFromLabelRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Uptempo")


if __name__ == '__main__':
    unittest.main()
