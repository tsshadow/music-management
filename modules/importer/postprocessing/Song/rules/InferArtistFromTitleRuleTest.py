import unittest
from unittest.mock import MagicMock
from postprocessing.Song.rules.InferArtistFromTitleRule import InferArtistFromTitleRule
from postprocessing.constants import TITLE, ARTIST, ORIGINAL_TITLE


class InferArtistFromTitleRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.tag_collection.set_item = MagicMock()
        self.song.tag_collection.set_artist = MagicMock()
        self.song.tag_collection.add = MagicMock()
        self.song.tag_collection.get_item_as_string = MagicMock()
        self.song.path = lambda: "/home/teun/Music/D-Fence/track.mp3"

        self.mock_artist_db = MagicMock()
        self.mock_artist_db.get_all_values.return_value = [
            "Noisekick", "D-Fence", "Angerfist", "Headhunterz", "Wildstylez",
            "D-Sturb", "Hans Glock", "Lunakorpz", "The Viper", "Unresolved", "Bloodlust"
        ]

        self.mock_genres_db = MagicMock()
        self.mock_genres_db.get_all.return_value = [
            "Hardstyle"
        ]

        self.mock_ignored_db = MagicMock()
        self.mock_ignored_db.get_all.return_value = []  # add e.g. ["vieze jack"] for ignore tests

    def _apply_rule(self, title):
        self.song.tag_collection.has_item.return_value = False
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: title,
            ORIGINAL_TITLE: title,
        }[key]
        self.song.tag_collection.get_item = MagicMock(return_value=title)
        rule = InferArtistFromTitleRule(
            artist_db=self.mock_artist_db,
            genre_db=self.mock_genres_db,
            ignored_db=self.mock_ignored_db
        )
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
        self.song.path = lambda: "/home/teun/Music/Angerfist/track.mp3"
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
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 - Pit II - Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 - Lunakorpz - Pit II")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes_incorrect_case(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 - LUNAKORPZ - Pit II")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes_extra_suffix(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 - LUNAKORPZ LIVE - Pit II")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes_pipe(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 | LUNAKORPZ LIVE - Pit II")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes_I(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 I Lunakorpz - Pit II ")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Pit II")

    def test_artist_in_middle_multiple_dashes_large(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Snakepit 2024 - Korpz live - Defqon edit - Lunakorpz - Pit II")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Lunakorpz")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Snakepit 2024 - Korpz live - Defqon edit - Pit II")

    def test_artist_in_middle_multiple_dashes_brackets(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Guardelion [Harder Class Winner] - Decibel outdoor 2023 - Future District - Saturday")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Guardelion")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Decibel outdoor 2023 - Future District - Saturday")

    def test_artist_in_middle_multiple_dashes_double_brackets(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("D-Sturb [Playground 04： Story] [LIVE] ｜ Decibel outdoor 2023 ｜ Mainstage ｜ Saturday")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "D-Sturb")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Decibel outdoor 2023 - Mainstage - Saturday")

    def test_artist_in_middle_multiple_dashes_genres(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Guardelion - Hardstyle - Future District - Saturday")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Guardelion")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Hardstyle - Future District - Saturday")

    def test_artist_in_middle_multiple_dashes_warmupmix(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Supersized Kingsday Festival 2023 ｜ warm-up mix The Viper")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "The Viper")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Supersized Kingsday Festival 2023 - warm-up mix")

    def test_noisekick(self):
        self.song.path = lambda: "/home/teun/Music/Snakepit/track.mp3"
        self._apply_rule("Noisekick @ Decibel outdoor 2019 - Terror - Saturday")
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Noisekick")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Decibel outdoor 2019 - Terror - Saturday")

    def test_artist_presents_preserve_title(self):
        self.song.path = lambda: "/home/teun/Music/Bloodlust/track.mp3"
        title = "Bloodlust presents: The Assassination | Decibel outdoor 2024 | Mainstage | SAVAGE SUNDAY"
        self._apply_rule(title)
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Bloodlust")

        # Make sure TITLE was not changed
        for call in self.song.tag_collection.set_item.call_args_list:
            assert call.args[0] != TITLE, f"Unexpected TITLE modification: {call}"

    def test_artist_colon_preserve_title(self):
        self.song.path = lambda: "/home/teun/Music/Unresolved/track.mp3"
        title = "Unresolved: Bad Blood LIVE | Decibel outdoor 2024 | Mainstage | SAVAGE SUNDAY"
        self._apply_rule(title)
        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Unresolved")

        # Make sure TITLE was not changed
        for call in self.song.tag_collection.set_item.call_args_list:
            assert call.args[0] != TITLE, f"Unexpected TITLE modification: {call}"

    def test_manual_test(self):
        self.song.path = lambda: "/home/teun/Music/The Viper/track.mp3"
        title = "Warface & Rooler @ Defqon.1 2025 ｜ The Gathering ｜ Blue Stage"
        self._apply_rule(title)

        self.song.tag_collection.set_item.assert_any_call(ARTIST, "Warface;Rooler")
        self.song.tag_collection.set_item.assert_any_call(TITLE, "Defqon.1 2025 ｜ The Gathering ｜ Blue Stage")

    def test_no_dash_in_title(self):
        self._apply_rule("Just One Part Title")
        self.song.tag_collection.set_artist.assert_not_called()
        self.song.tag_collection.set_item.assert_any_call(ORIGINAL_TITLE, "Just One Part Title")

    def test_original_is_set(self):
        self._apply_rule("Headhunterz - From Within")
        self.song.tag_collection.set_item.assert_any_call(ORIGINAL_TITLE, "Headhunterz - From Within")

    def test_idempotent_rule_application(self):
        title = "D-Fence - Emporium 2025"
        self.song.tag_collection.has_item.return_value = False
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: "",
            TITLE: title,
            ORIGINAL_TITLE: title,
        }[key]
        self.song.tag_collection.get_item = MagicMock(return_value=title)

        rule = InferArtistFromTitleRule(
            artist_db=self.mock_artist_db,
            genre_db=self.mock_genres_db,
            ignored_db=self.mock_ignored_db
        )

        # Run rule once
        rule.apply(self.song)
        first_calls = [
            call for call in self.song.tag_collection.set_item.call_args_list
            if call.args[0] != ORIGINAL_TITLE
        ]

        # Clear mocks and re-run
        self.song.tag_collection.set_item.reset_mock()
        self.song.tag_collection.set_artist.reset_mock()
        self.song.tag_collection.add.reset_mock()

        # Pretend the ORIGINAL_TITLE is now set
        self.song.tag_collection.has_item.return_value = True
        rule.apply(self.song)
        second_calls = [
            call for call in self.song.tag_collection.set_item.call_args_list
            if call.args[0] != ORIGINAL_TITLE
        ]

        self.assertEqual(first_calls, second_calls,
                         "Repeated rule application should yield identical tag changes (except for ORIGINAL_TITLE)")
