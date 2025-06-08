import unittest
from unittest.mock import MagicMock
from postprocessing.Song.rules.CleanAndFilterGenreRule import CleanAndFilterGenreRule



class CleanAndFilterGenreRuleTest(unittest.TestCase):
    def test_corrects_and_sorts_genres(self):
        tag = MagicMock()
        tag.to_array.return_value = ["rawstyle", "hardstyle"]
        helper = MagicMock()
        helper.get_corrected_or_exists.side_effect = lambda g: g.capitalize()

        tag_collection = MagicMock()
        tag_collection.has_item.return_value = True
        tag_collection.get_item.return_value = tag

        song = MagicMock()
        song.tag_collection = tag_collection
        song.path.return_value = "song.mp3"

        rule = CleanAndFilterGenreRule(helper)
        rule.apply(song)

        tag.set.assert_called_once_with(["Hardstyle", "Rawstyle"])