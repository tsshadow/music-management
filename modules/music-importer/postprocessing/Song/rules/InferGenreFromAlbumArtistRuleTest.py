import unittest
from unittest.mock import MagicMock

from postprocessing.Song.rules.InferGenreFromAlbumArtistRule import InferGenreFromAlbumArtistRule
from postprocessing.constants import GENRE, ALBUM_ARTIST


class InferGenreFromAlbumArtistRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.merge_and_sort_genres = lambda a, b: sorted(set(a + b))
        self.song.tag_collection.set_item = MagicMock()

    def test_does_not_duplicate_existing_genre(self):
        self.song.tag_collection.get_item_as_string = MagicMock(return_value="Neophyte")
        self.song.tag_collection.get_item_as_array = MagicMock(return_value=["Hardcore"])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Hardcore"])  # al bestaand

        rule = InferGenreFromAlbumArtistRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Hardcore")

    def test_adds_new_genre(self):
        self.song.tag_collection.get_item_as_string = MagicMock(return_value="Neophyte")
        self.song.tag_collection.get_item_as_array = MagicMock(return_value=["Hardcore"])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Industrial"])

        rule = InferGenreFromAlbumArtistRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Hardcore;Industrial")

    def test_sets_genre_when_none_exist(self):
        self.song.tag_collection.get_item_as_string = MagicMock(return_value="Neophyte")
        self.song.tag_collection.get_item_as_array = MagicMock(return_value=[])

        helper = MagicMock()
        helper.get = MagicMock(return_value=["Uptempo"])

        rule = InferGenreFromAlbumArtistRule(helper=helper)
        rule.apply(self.song)

        self.song.tag_collection.set_item.assert_called_once_with(GENRE, "Uptempo")


if __name__ == '__main__':
    unittest.main()
