import unittest
from unittest.mock import MagicMock

from postprocessing.Song.rules.InferGenreFromSubgenreRule import InferGenreFromSubgenreRule
from postprocessing.constants import GENRE


class InferGenreFromSubgenreRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.merge_and_sort_genres = lambda a, b: sorted(set(a + b))
        self.song.tag_collection.set_item = MagicMock()

    def test_adds_broader_genre_from_subgenre(self):
        """Voegt bredere genre toe als die via lookup gevonden wordt."""
        self.song.tag_collection.get_item_as_array = MagicMock(return_value=["Uptempo Hardcore"])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Hardcore"])

        rule = InferGenreFromSubgenreRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Hardcore;Uptempo Hardcore")

    def test_no_change_when_no_lookup_match(self):
        """Laat genre ongemoeid als er geen match is."""
        self.song.tag_collection.get_item_as_array = MagicMock(return_value=["Techno"])

        helper = MagicMock()
        helper.get = MagicMock(return_value=None)

        rule = InferGenreFromSubgenreRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Techno")

    def test_avoids_duplicates(self):
        """Voegt geen dubbele genres toe."""
        self.song.tag_collection.get_item_as_array = MagicMock(return_value=["Hardcore"])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Hardcore"])  # zelfde als al bestaand genre

        rule = InferGenreFromSubgenreRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Hardcore")


if __name__ == '__main__':
    unittest.main()
