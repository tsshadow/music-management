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
            "D-Fence", "Angerfist", "Headhunterz", "Wildstylez", "D-Sturb", "Hans Glock", "Lunakorpz"
        ]

    def _apply_rule(self, title):
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: title
        }[key]
        rule = InferArtistFromTitleRule(artist_db=self.mock_artist_db)
        rule.apply(self.song)

# @
    def test_artist_at_event(self):
        self._apply_rule("D-Fence @ Emporium 2024")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "D-Fence")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Emporium 2024")

    def test_multiple_artists_at_event(self):
        self._apply_rule("D-Fence & Vieze Jack @ Emporium 2024")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "D-Fence;Vieze Jack")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Emporium 2024")

# by
    def test_title_by_artist(self):
        self.song.path = lambda: "/home/user/Music/Angerfist/track.mp3"
        self._apply_rule("Kick It Hard by Angerfist")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Angerfist")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Kick It Hard")

    def test_title_by_multiple_artists(self):
        self._apply_rule("Kick It Hard by Angerfist & MC Tha Watcher")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Angerfist;MC Tha Watcher")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Kick It Hard")

# -
    def test_exact_artist_match(self):
        self._apply_rule("D-Fence - Emporium 2025")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "D-Fence")

    def test_multiple_artists_in_artist_field(self):
        self._apply_rule("Headhunterz vs Wildstylez - The Return Of Headhunterz")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Headhunterz;Wildstylez")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "The Return Of Headhunterz")

    def test_exact_artist_match_reverse(self):
        self._apply_rule("Emporium 2025 - D-Fence")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Emporium 2025")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "D-Fence")

    def test_exact_artist_match_reverse_multiple_artists(self):
        self._apply_rule("Emporium 2025 - D-Sturb and Hans Glock")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Emporium 2025")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "D-Sturb;Hans Glock")

    def test_fuzzy_artist_match(self):
        self._apply_rule("D.Fence - Emporium 2025")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "D.Fence")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Emporium 2025")

    def test_fallback_to_first_part(self):
        self._apply_rule("UnknownGuy - Cool Track")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "UnknownGuy")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Cool Track")

# Multiple -
    def test_artist_at_end_multiple_dashes(self):
        self.song.path = lambda: "/home/user/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 - Pit II - Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes(self):
        self.song.path = lambda: "/home/user/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 - Lunakorpz - Pit II")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes_incorrect_case(self):
        self.song.path = lambda: "/home/user/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 - LUNAKORPZ - Pit II")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes_extra_suffix(self):
        self.song.path = lambda: "/home/user/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 - LUNAKORPZ LIVE - Pit II")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes_pipe(self):
        self.song.path = lambda: "/home/user/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 | LUNAKORPZ LIVE - Pit II")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes_I(self):
        self.song.path = lambda: "/home/user/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 I Lunakorpz - Pit II ")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes_large(self):
        self.song.path = lambda: "/home/user/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 - Korpz live - Defqon edit - Lunakorpz - Pit II")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Korpz live - Defqon edit - Pit II")


# Fallbacks
    def test_no_dash_in_title(self):
        self._apply_rule("Just One Part Title")
        self.song.tag_collection.set_item.assert_not_called()
        self.song.tag_collection.set_artist.assert_not_called()
