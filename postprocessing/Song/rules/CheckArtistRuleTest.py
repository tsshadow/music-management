import unittest
from unittest.mock import MagicMock
from postprocessing.Song.rules.CheckArtistRule import CheckArtistRule
from postprocessing.constants import ARTIST


class CheckArtistRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.tag_item = MagicMock()
        self.song.artists.return_value = ["Wrong Artist", "Known Artist"]
        self.song.tag_collection.get_item.return_value = self.tag_item

        self.artist_table = MagicMock()
        self.ignored_table = MagicMock()

    def test_adds_canonical_name_if_artist_known(self):
        self.artist_table.exists.side_effect = lambda x: x == "Known Artist"
        self.artist_table.get.side_effect = lambda x: x.upper()  # Simuleer kapitalisatie
        self.ignored_table.get_corrected.return_value = None
        self.ignored_table.exists.return_value = False

        rule = CheckArtistRule(self.artist_table, self.ignored_table)
        rule.apply(self.song)

        self.tag_item.add.assert_any_call("KNOWN ARTIST")

    def test_corrected_artist_is_used_if_known_in_ignored(self):
        self.artist_table.exists.return_value = False
        self.ignored_table.get_corrected.side_effect = lambda x: "Corrected Artist" if x == "Wrong Artist" else None
        self.ignored_table.exists.return_value = False

        rule = CheckArtistRule(self.artist_table, self.ignored_table)
        rule.apply(self.song)

        self.tag_item.remove.assert_any_call("Wrong Artist")
        self.tag_item.add.assert_any_call("Corrected Artist")

    def test_removes_artist_if_in_ignored_without_correction(self):
        self.artist_table.exists.return_value = False
        self.ignored_table.get_corrected.return_value = None
        self.ignored_table.exists.side_effect = lambda x: x == "Wrong Artist"

        rule = CheckArtistRule(self.artist_table, self.ignored_table)
        rule.apply(self.song)

        self.tag_item.remove.assert_any_call("Wrong Artist")

    def test_does_nothing_if_unknown_artist(self):
        self.artist_table.exists.return_value = False
        self.ignored_table.get_corrected.return_value = None
        self.ignored_table.exists.return_value = False

        rule = CheckArtistRule(self.artist_table, self.ignored_table)
        rule.apply(self.song)

        # Niets toevoegen of verwijderen
        self.tag_item.add.assert_not_called()
        self.tag_item.remove.assert_not_called()
        self.ignored_table.delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
