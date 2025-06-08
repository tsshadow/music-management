import unittest
from unittest.mock import MagicMock
from postprocessing.Song.rules.InferArtistFromTitleRule import InferArtistFromTitleRule
from postprocessing.constants import TITLE, ARTIST


class InferArtistFromTitleRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.tag_collection.set_item = MagicMock()
        self.song.tag_collection.set_artist = MagicMock()
        self.song.tag_collection.add = MagicMock()
        self.song.tag_collection.get_item_as_string = MagicMock()
        self.song.path = lambda: "/home/user/Music/D-Fence/track.mp3"

        self.mock_artist_db = MagicMock()
        self.mock_artist_db.get_all_values.return_value = [
            "D-Fence", "Angerfist", "Headhunterz", "Wildstylez", "D-Sturb", "Hans Glock"
        ]

    def test_artist_at_event(self):
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "D-Fence",
            TITLE: "D-Fence @ Emporium 2024"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.add.assert_called_with(ARTIST, "D-Fence")
        self.song.tag_collection.set_item.assert_called_with(TITLE, "Emporium 2024")

    def test_multiple_artists_at_event(self):
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "D-Fence",
            TITLE: "D-Fence & Vieze Jack @ Emporium 2024"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.add.assert_any_call(ARTIST, "D-Fence;Vieze Jack")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Emporium 2024")

    def test_title_by_artist(self):
        self.song.path = lambda: "/home/user/Music/Angerfist/track.mp3"
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: "Kick It Hard by Angerfist"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.add.assert_called_with(ARTIST, "Angerfist")
        self.song.tag_collection.set_item.assert_called_with(TITLE, "Kick It Hard")

    def test_title_by_multiple_artists(self):
        self.song.path = lambda: "/home/user/Music/Angerfist/track.mp3"
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: "Kick It Hard by Angerfist & MC Tha Watcher"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.add.assert_called_with(ARTIST, "Angerfist;MC Tha Watcher")
        self.song.tag_collection.set_item.assert_called_with(TITLE, "Kick It Hard")

    def test_exact_artist_match(self):
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: "D-Fence - Emporium 2025"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "D-Fence")

    def test_multiple_artists_in_artist_field(self):
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: "Headhunterz vs Wildstylez - The Return Of Headhunterz"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Headhunterz;Wildstylez")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "The Return Of Headhunterz")

    def test_exact_artist_match_reverse(self):
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: "Emporium 2025 - D-Fence"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Emporium 2025")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "D-Fence")

    def test_exact_artist_match_reverse_multiple_artists(self):
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: "Emporium 2025 - D-Sturb and Hans Glock"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Emporium 2025")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "D-Sturb;Hans Glock")

    def test_fuzzy_artist_match(self):
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: "D.Fence - Emporium 2025"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.add.assert_any_call(ARTIST, "D.Fence")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Emporium 2025")

    def test_fallback_to_first_part(self):
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: "UnknownGuy - Cool Track"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.add.assert_any_call(ARTIST, "UnknownGuy")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Cool Track")

    def test_no_dash_in_title(self):
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: "Just One Part Title"
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)
        self.song.tag_collection.set_item.assert_not_called()
        self.song.tag_collection.set_artist.assert_not_called()


if __name__ == '__main__':
    unittest.main()
