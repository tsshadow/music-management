import unittest
from unittest.mock import MagicMock

from postprocessing.Song.rules.InferGenreFromArtistRule import InferGenreFromArtistRule
from postprocessing.constants import ARTIST, GENRE


class InferGenreFromArtistRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.merge_and_sort_genres = lambda a, b: sorted(set(a + b))
        self.song.tag_collection.set_item = MagicMock()

    def test_does_not_duplicate_existing_genre(self):
        """Voegt geen genre toe als het al in de lijst zit."""
        self.song.tag_collection.get_item_as_array = MagicMock(side_effect=lambda key: {
            ARTIST: ["Angerfist"],
            GENRE: ["Hardcore"]
        }[key])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Hardcore"])  # al bestaand genre

        rule = InferGenreFromArtistRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Hardcore")

    def test_adds_new_genre(self):
        """Voegt een nieuwe genre toe aan de bestaande lijst."""
        self.song.tag_collection.get_item_as_array = MagicMock(side_effect=lambda key: {
            ARTIST: ["Angerfist"],
            GENRE: ["Hardcore"]
        }[key])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Industrial"])  # nieuw genre

        rule = InferGenreFromArtistRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Hardcore;Industrial")

    def test_sets_genre_when_none_exist(self):
        """Zet genre als er nog geen genres aanwezig zijn."""
        self.song.tag_collection.get_item_as_array = MagicMock(side_effect=lambda key: {
            ARTIST: ["Angerfist"],
            GENRE: []
        }[key])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Genre1"])

        rule = InferGenreFromArtistRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Genre1")


if __name__ == '__main__':
    unittest.main()
