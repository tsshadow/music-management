import unittest
from unittest.mock import MagicMock
from postprocessing.Song.rules.CleanArtistFieldsRule import CleanArtistFieldsRule



class CleanArtistFieldsRuleTest(unittest.TestCase):
    def test_cleans_artist_and_album_artist(self):
        tag = MagicMock()
        tag_collection = MagicMock()
        tag_collection.has_item.side_effect = lambda k: True
        tag_collection.get_item.side_effect = lambda k: tag

        song = MagicMock()
        song.tag_collection = tag_collection

        rule = CleanArtistFieldsRule()
        rule.apply(song)

        tag.regex.assert_called()
        tag.special_recapitalize.assert_called()
        tag.strip.assert_called()