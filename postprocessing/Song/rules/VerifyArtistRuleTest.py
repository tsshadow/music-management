import unittest
from unittest.mock import MagicMock, patch

from postprocessing.Song.rules.VerifyArtistRule import VerifyArtistRule
from postprocessing.Song.rules.TagResult import TagResultType


class VerifyArtistRuleTest(unittest.TestCase):
    def setUp(self):
        self.tag = MagicMock()
        self.song = MagicMock()
        self.song.artist.return_value = "Unknown"
        self.song.tag_collection.get_item.return_value = self.tag
        self.artist_db = MagicMock()

    def test_existing_artist_updates_casing(self):
        self.song.artist.return_value = "angerfist"
        self.artist_db.exists.return_value = True
        self.artist_db.get.return_value = "Angerfist"
        rule = VerifyArtistRule(self.artist_db)

        result = rule.apply(self.song)

        self.tag.remove.assert_called_once_with("angerfist")
        self.tag.add.assert_called_once_with("Angerfist")
        self.assertEqual(result.result_type, TagResultType.UPDATED)
        self.assertEqual(result.value, "Angerfist")

    @patch("postprocessing.Song.rules.ExternalArtistLookup.ExternalArtistLookup.is_known_artist", return_value=True)
    def test_external_lookup_adds_artist(self, mock_lookup):
        self.song.artist.return_value = "New Artist"
        self.artist_db.exists.return_value = False
        # simulate insert_if_not_exists callable
        self.artist_db.insert_if_not_exists = MagicMock()
        rule = VerifyArtistRule(self.artist_db)

        result = rule.apply(self.song)

        self.artist_db.insert_if_not_exists.assert_called_once_with("New Artist")
        self.assertEqual(result.result_type, TagResultType.VALID)

    def test_numeric_only_artist_is_ignored(self):
        self.song.artist.return_value = "001"
        self.artist_db.exists.return_value = False
        rule = VerifyArtistRule(self.artist_db)

        result = rule.apply(self.song)

        self.tag.remove.assert_called_once_with("001")
        self.assertEqual(result.result_type, TagResultType.IGNORED)

    def test_numeric_prefix_is_stripped(self):
        self.song.artist.return_value = "005. Radical Redemption"
        self.artist_db.exists.return_value = False
        rule = VerifyArtistRule(self.artist_db)

        result = rule.apply(self.song)

        self.tag.remove.assert_called_once_with("005. Radical Redemption")
        self.tag.add.assert_called_once_with("Radical Redemption")
        self.assertEqual(result.result_type, TagResultType.UPDATED)

    def test_placeholder_artist_is_ignored(self):
        self.song.artist.return_value = "Unknown Artist"
        self.artist_db.exists.return_value = False
        rule = VerifyArtistRule(self.artist_db)

        result = rule.apply(self.song)

        self.tag.remove.assert_called_once_with("Unknown Artist")
        self.assertEqual(result.result_type, TagResultType.IGNORED)


if __name__ == "__main__":
    unittest.main()
