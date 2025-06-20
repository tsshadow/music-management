import unittest
from unittest.mock import MagicMock, call
from postprocessing.Song.rules.InferRemixerFromTitleRule import InferRemixerFromTitleRule
from postprocessing.constants import ARTIST, TITLE, REMIXER


class InferRemixerFromTitleRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.split_artists = lambda s: [a.strip() for a in s.split("&")]

        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            TITLE: self.title,
            ARTIST: "Original Artist"
        }[key]

        self.artist_tag = MagicMock()
        self.artist_tag.to_array.return_value = []
        self.artist_tag.to_string.return_value = ""
        self.artist_tag.changed = False

        self.remixers_tag = MagicMock()
        self.remixers_tag.to_array.return_value = []
        self.remixers_tag.to_string.return_value = ""
        self.remixers_tag.changed = False

        self.song.tag_collection.get_item.side_effect = lambda key: {
            ARTIST: self.artist_tag,
            REMIXER: self.remixers_tag
        }[key]

        self.song.tag_collection.has_item.side_effect = lambda key: key in [ARTIST, REMIXER]

        self.artist_db = MagicMock()
        self.artist_db.get.side_effect = lambda x: x.title()
        self.artist_db.exists.side_effect = lambda x: True
        self.ignored_db = MagicMock()
        self.ignored_db.exists.side_effect = lambda x: False

        self.rule = InferRemixerFromTitleRule(artist_db=self.artist_db, ignored_db=self.ignored_db)

    def assertArtistAdded(self, name):
        self.artist_tag.add.assert_any_call(name)

    def assertRemixerAdded(self, name):
        self.remixers_tag.add.assert_any_call(name)

    def test_adjuzt_remix(self):
        self.title = "CPU (Adjuzt Remix)"
        self.rule.apply(self.song)
        self.assertArtistAdded("Adjuzt")
        self.assertRemixerAdded("Adjuzt")

    def test_multiple_artists(self):
        self.title = "Catastrophy (Neophyte & Karun Remix)"
        self.rule.apply(self.song)
        self.assertArtistAdded("Neophyte")
        self.assertRemixerAdded("Neophyte")
        self.assertArtistAdded("Karun")
        self.assertRemixerAdded("Karun")

    def test_suffix_cleanup(self):
        self.title = "Catastrophy (Karun Remix Extended)"
        self.rule.apply(self.song)
        self.assertArtistAdded("Karun")
        self.assertRemixerAdded("Karun")

    def test_ignored_artist_is_removed(self):
        self.title = "CPU (IgnoredGuy Remix)"
        self.artist_db.exists.side_effect = lambda x: False
        self.artist_db.get.side_effect = lambda x: None
        self.ignored_db.exists.side_effect = lambda x: x.lower() == "ignoredguy"
        self.ignored_db.get_corrected.return_value = None  #
        self.rule.apply(self.song)
        self.artist_tag.remove.assert_called_with("IgnoredGuy")
    #
    # def test_unknown_artist_skipped_by_input(self):
    #     self.title = "CPU (Mysteryman Remix)"
    #     self.artist_db.get.side_effect = lambda x: x.title()
    #     self.artist_db.exists.side_effect = lambda x: False
    #     with unittest.mock.patch("builtins.input", return_value="n"):
    #         self.rule.apply(self.song)
    #     self.assertNotIn(call("Mysteryman"), self.artist_tag.add.mock_calls)
    #
    # def test_adds_after_confirmation(self):
    #     self.title = "CPU (NewArtist Bootleg)"
    #     self.artist_db.exists.side_effect = lambda x: False if x == "Newartist" else True
    #     self.artist_db.get.side_effect = lambda x: x.title()
    #     with unittest.mock.patch("builtins.input", return_value="y"):
    #         self.rule.apply(self.song)
    #     self.assertArtistAdded("Newartist")
    #     self.assertRemixerAdded("Newartist")
    #     self.artist_db.add.assert_called_once_with("Newartist")

    def test_adds_nothing_without_bracketed_segment(self):
        self.title = "CPU - Edit by Adjuzt"
        self.rule.apply(self.song)
        self.artist_tag.add.assert_not_called()
        self.remixers_tag.add.assert_not_called()

    def test_numeric_segment_ignored(self):
        self.title = "CPU (2023 Remix)"
        self.artist_db.get.side_effect = lambda x: x.title()
        self.rule.apply(self.song)
        self.artist_tag.add.assert_not_called()

    def test_does_not_duplicate_existing_artist(self):
        self.title = "CPU (Adjuzt Remix)"
        self.artist_tag.to_array.return_value = ["Adjuzt"]
        self.remixers_tag.to_array.return_value = ["Adjuzt"]
        self.rule.apply(self.song)
        self.artist_tag.add.assert_not_called()
        self.remixers_tag.add.assert_not_called()

    def test_apostrophe_s_removal(self):
        self.title = "Trackname (Mainstage Maffia's Remix)"
        self.rule.apply(self.song)
        self.assertArtistAdded("Mainstage Maffia'S")
        self.assertRemixerAdded("Mainstage Maffia'S")

    def test_year_suffix_is_removed(self):
        self.title = "Song (Karun Remix 2024)"
        self.rule.apply(self.song)
        self.assertArtistAdded("Karun")
        self.assertRemixerAdded("Karun")

    def test_2k_year_suffix_is_removed(self):
        self.title = "Song (Karun Remix 2k23)"
        self.rule.apply(self.song)
        self.assertArtistAdded("Karun")
        self.assertRemixerAdded("Karun")


if __name__ == '__main__':
    unittest.main()
