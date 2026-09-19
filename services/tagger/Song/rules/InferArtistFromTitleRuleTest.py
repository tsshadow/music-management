import random
import string
import unittest
from difflib import get_close_matches
from unittest.mock import MagicMock

from services.tagger.constants import ARTIST, ORIGINAL_TITLE, TITLE
from services.tagger.Song.rules.InferArtistFromTitleRule import (
    InferArtistFromTitleRule,
    has_close_artist,
    set_cleaned_artist,
)


class InferArtistFromTitleRuleTest(unittest.TestCase):
    def setUp(self):
        self.song = MagicMock()
        self.song.tag_collection.set_item = MagicMock()
        self.song.tag_collection.set_artist = MagicMock()
        self.song.tag_collection.add = MagicMock()
        self.song.tag_collection.get_item_as_string = MagicMock()
        self.song.path = lambda: '/home/user/Music/D-Fence/track.mp3'
        self.mock_artist_db = MagicMock()
        self.mock_artist_db.get_all_values.return_value = [
            'Noisekick',
            'D-Fence',
            'Angerfist',
            'Headhunterz',
            'Wildstylez',
            'D-Sturb',
            'Hans Glock',
            'Lunakorpz',
            'The Viper',
            'Unresolved',
            'Bloodlust',
        ]
        self.mock_genres_db = MagicMock()
        self.mock_genres_db.get_all.return_value = ['Hardstyle']
        self.mock_ignored_db = MagicMock()
        self.mock_ignored_db.get_all.return_value = []

    def _apply_rule(self, title):
        self.song.tag_collection.has_item.return_value = False
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: '',
            TITLE: title,
            ORIGINAL_TITLE: title,
        }[key]
        self.song.tag_collection.get_item = MagicMock(return_value=title)
        rule = InferArtistFromTitleRule(
            artist_db=self.mock_artist_db, genre_db=self.mock_genres_db, ignored_db=self.mock_ignored_db
        )
        rule.apply(self.song)

    def test_artist_at_event(self):
        self._apply_rule('D-Fence @ Emporium 2024')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'D-Fence')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Emporium 2024')

    def test_multiple_artists_at_event(self):
        self._apply_rule('D-Fence & Vieze Jack @ Emporium 2024')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'D-Fence;Vieze Jack')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Emporium 2024')

    def test_title_by_artist(self):
        self.song.path = lambda: '/home/user/Music/Angerfist/track.mp3'
        self._apply_rule('Kick It Hard by Angerfist')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Angerfist')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Kick It Hard')

    def test_title_by_multiple_artists(self):
        self._apply_rule('Kick It Hard by Angerfist & MC Tha Watcher')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Angerfist;MC Tha Watcher')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Kick It Hard')

    def test_exact_artist_match(self):
        self._apply_rule('D-Fence - Emporium 2025')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'D-Fence')

    def test_multiple_artists_in_artist_field(self):
        self._apply_rule('Headhunterz vs Wildstylez - The Return Of Headhunterz')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Headhunterz;Wildstylez')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'The Return Of Headhunterz')

    def test_exact_artist_match_reverse(self):
        self._apply_rule('Emporium 2025 - D-Fence')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Emporium 2025')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'D-Fence')

    def test_exact_artist_match_reverse_multiple_artists(self):
        self._apply_rule('Emporium 2025 - D-Sturb and Hans Glock')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Emporium 2025')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'D-Sturb;Hans Glock')

    def test_fuzzy_artist_match(self):
        self._apply_rule('D.Fence - Emporium 2025')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'D.Fence')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Emporium 2025')

    def test_fallback_to_first_part(self):
        self._apply_rule('UnknownGuy - Cool Track')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'UnknownGuy')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Cool Track')

    def test_artist_at_end_multiple_dashes(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Snakepit 2024 - Pit II - Lunakorpz')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Lunakorpz')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Snakepit 2024 - Pit II')

    def test_artist_in_middle_multiple_dashes(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Snakepit 2024 - Lunakorpz - Pit II')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Lunakorpz')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Snakepit 2024 - Pit II')

    def test_artist_in_middle_multiple_dashes_incorrect_case(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Snakepit 2024 - LUNAKORPZ - Pit II')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Lunakorpz')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Snakepit 2024 - Pit II')

    def test_artist_in_middle_multiple_dashes_extra_suffix(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Snakepit 2024 - LUNAKORPZ LIVE - Pit II')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Lunakorpz')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Snakepit 2024 - Pit II')

    def test_artist_in_middle_multiple_dashes_pipe(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Snakepit 2024 | LUNAKORPZ LIVE - Pit II')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Lunakorpz')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Snakepit 2024 - Pit II')

    def test_artist_in_middle_multiple_dashes_I(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Snakepit 2024 I Lunakorpz - Pit II ')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Lunakorpz')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Snakepit 2024 - Pit II')

    def test_artist_in_middle_multiple_dashes_large(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Snakepit 2024 - Korpz live - Defqon edit - Lunakorpz - Pit II')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Lunakorpz')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Snakepit 2024 - Korpz live - Defqon edit - Pit II')

    def test_artist_in_middle_multiple_dashes_brackets(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Guardelion [Harder Class Winner] - Decibel outdoor 2023 - Future District - Saturday')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Guardelion')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Decibel outdoor 2023 - Future District - Saturday')

    def test_artist_in_middle_multiple_dashes_double_brackets(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('D-Sturb [Playground 04： Story] [LIVE] ｜ Decibel outdoor 2023 ｜ Mainstage ｜ Saturday')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'D-Sturb')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Decibel outdoor 2023 - Mainstage - Saturday')

    def test_artist_in_middle_multiple_dashes_genres(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Guardelion - Hardstyle - Future District - Saturday')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Guardelion')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Hardstyle - Future District - Saturday')

    def test_artist_in_middle_multiple_dashes_warmupmix(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Supersized Kingsday Festival 2023 ｜ warm-up mix The Viper')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'The Viper')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Supersized Kingsday Festival 2023 - warm-up mix')

    def test_noisekick(self):
        self.song.path = lambda: '/home/user/Music/Snakepit/track.mp3'
        self._apply_rule('Noisekick @ Decibel outdoor 2019 - Terror - Saturday')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Noisekick')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Decibel outdoor 2019 - Terror - Saturday')

    def test_artist_presents_title_stripped(self):
        self.song.path = lambda: '/home/user/Music/Bloodlust/track.mp3'
        title = 'Bloodlust presents: The Assassination | Decibel outdoor 2024 | Mainstage | SAVAGE SUNDAY'
        self._apply_rule(title)
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Bloodlust')
        self.song.tag_collection.set_item.assert_any_call(
            TITLE, 'The Assassination | Decibel outdoor 2024 | Mainstage | SAVAGE SUNDAY'
        )

    def test_artist_colon_title_stripped(self):
        self.song.path = lambda: '/home/user/Music/Unresolved/track.mp3'
        title = 'Unresolved: Bad Blood LIVE | Decibel outdoor 2024 | Mainstage | SAVAGE SUNDAY'
        self._apply_rule(title)
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Unresolved')
        self.song.tag_collection.set_item.assert_any_call(
            TITLE, 'Bad Blood LIVE | Decibel outdoor 2024 | Mainstage | SAVAGE SUNDAY'
        )

    def test_manual_test(self):
        self.song.path = lambda: '/home/user/Music/The Viper/track.mp3'
        title = 'Warface & Rooler @ Defqon.1 2025 ｜ The Gathering ｜ Blue Stage'
        self._apply_rule(title)
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Warface;Rooler')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Defqon.1 2025 ｜ The Gathering ｜ Blue Stage')

    def test_no_dash_in_title(self):
        self._apply_rule('Just One Part Title')
        self.song.tag_collection.set_artist.assert_not_called()
        self.song.tag_collection.set_item.assert_any_call(ORIGINAL_TITLE, 'Just One Part Title')

    def test_original_is_set(self):
        self._apply_rule('Headhunterz - From Within')
        self.song.tag_collection.set_item.assert_any_call(ORIGINAL_TITLE, 'Headhunterz - From Within')

    def test_idempotent_rule_application(self):
        title = 'D-Fence - Emporium 2025'
        self.song.tag_collection.has_item.return_value = False
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: '',
            TITLE: title,
            ORIGINAL_TITLE: title,
        }[key]
        self.song.tag_collection.get_item = MagicMock(return_value=title)
        rule = InferArtistFromTitleRule(
            artist_db=self.mock_artist_db, genre_db=self.mock_genres_db, ignored_db=self.mock_ignored_db
        )
        rule.apply(self.song)
        first_calls = [
            call for call in self.song.tag_collection.set_item.call_args_list if call.args[0] != ORIGINAL_TITLE
        ]
        self.song.tag_collection.set_item.reset_mock()
        self.song.tag_collection.set_artist.reset_mock()
        self.song.tag_collection.add.reset_mock()
        self.song.tag_collection.has_item.return_value = True
        rule.apply(self.song)
        second_calls = [
            call for call in self.song.tag_collection.set_item.call_args_list if call.args[0] != ORIGINAL_TITLE
        ]
        self.assertEqual(
            first_calls,
            second_calls,
            'Repeated rule application should yield identical tag changes (except for ORIGINAL_TITLE)',
        )


class PromoMarkerIsNotAnArtistTest(unittest.TestCase):
    """A marker on the ignore list may not be picked out of a title, even from library_artists.

    "PREMIERE ｜ TARS - Rumble" put 9.188 production tracks under a non-existent artist called
    Premiere, because the marker had entered library_artists on an earlier pass and from then on
    matched itself better than any real name in the title could.
    """

    def setUp(self):
        self.song = MagicMock()
        self.song.path = lambda: '/home/user/Music/Kerbela/track.mp3'
        self.artist_db = MagicMock()
        self.artist_db.get_all_values.return_value = ['Premiere', 'TARS', 'Angerfist', 'Bootleg Boy']
        self.genres_db = MagicMock()
        self.genres_db.get_all.return_value = ['Hardstyle']
        self.ignored_db = MagicMock()
        self.ignored_db.get_all.return_value = []
        self.ignored_db.get_corrected.return_value = ''

    def _apply(self, title):
        self.song.tag_collection.has_item.return_value = False
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: '',
            TITLE: title,
            ORIGINAL_TITLE: title,
        }[key]
        self.song.tag_collection.get_item = MagicMock(return_value=title)
        rule = InferArtistFromTitleRule(artist_db=self.artist_db, genre_db=self.genres_db, ignored_db=self.ignored_db)
        rule.apply(self.song)

    def test_the_marker_wins_while_it_is_not_on_the_ignore_list(self):
        self._apply('PREMIERE ｜ TARS - Rumble [NNVA03]')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Premiere')

    def test_the_real_artist_wins_once_the_marker_is_ignored(self):
        self.ignored_db.get_all.return_value = ['Premiere']
        self._apply('PREMIERE ｜ TARS - Rumble [NNVA03]')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'TARS')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'PREMIERE - Rumble [NNVA03]')

    def test_an_ignored_marker_is_not_guessed_by_the_last_resort_rule(self):
        self.ignored_db.get_all.return_value = ['Premiere']
        self._apply('PREMIERE ｜ Someone Unknown - Rumble')
        written = [c for c in self.song.tag_collection.set_item.call_args_list if c.args[0] == ARTIST]
        assert written == [], written

    def test_a_fullwidth_pipe_never_ends_up_inside_an_artist_name(self):
        self.ignored_db.get_all.return_value = []
        self._apply('Nobody Known ｜ Someone Unknown - Rumble')
        for call in self.song.tag_collection.set_item.call_args_list:
            if call.args[0] == ARTIST:
                assert '｜' not in call.args[1], call.args[1]

    def test_an_ignored_name_with_a_correction_stays_selectable(self):
        self.ignored_db.get_all.return_value = ['Bootleg Boy']
        self.ignored_db.get_corrected.side_effect = lambda name: 'Bootleg Boy Official'
        self._apply('Bootleg Boy - Rumble')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Bootleg Boy')


class InferArtistFromEventPrefixRuleTest(unittest.TestCase):
    """A title that opens with the event names the artists on the other side."""

    def setUp(self):
        self.song = MagicMock()
        self.song.path = lambda: '/mnt/music/Soundcloud/Thunderdome/track.mp3'
        self.mock_artist_db = MagicMock()
        self.mock_artist_db.get_all_values.return_value = ['Akimbo', 'Barber', 'Akira', 'D-Fence']
        self.mock_genres_db = MagicMock()
        self.mock_genres_db.get_all.return_value = ['Hardcore']
        self.mock_ignored_db = MagicMock()
        self.mock_ignored_db.get_all.return_value = []
        self.mock_festival_helper = MagicMock()
        self.mock_festival_helper.get.return_value = None

    def _apply_rule(self, title, known_artists=None):
        if known_artists is not None:
            self.mock_artist_db.get_all_values.return_value = known_artists
        self.song.tag_collection.reset_mock()
        self.song.tag_collection.has_item.return_value = False
        self.song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: '',
            TITLE: title,
            ORIGINAL_TITLE: title,
        }[key]
        self.song.tag_collection.get_item = MagicMock(return_value=title)
        rule = InferArtistFromTitleRule(
            artist_db=self.mock_artist_db,
            genre_db=self.mock_genres_db,
            ignored_db=self.mock_ignored_db,
            festival_helper=self.mock_festival_helper,
        )
        rule.apply(self.song)

    def _artist_calls(self):
        return [call.args[1] for call in self.song.tag_collection.set_item.call_args_list if call.args[0] == ARTIST]

    def test_event_year_prefix_with_two_artists(self):
        self._apply_rule('Thunderdome 2025 ｜ Akimbo vs. Barber')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Akimbo;Barber')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Thunderdome 2025')

    def test_event_year_prefix_with_single_artist(self):
        self._apply_rule('Thunderdome 2025 ｜ Akira')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Akira')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Thunderdome 2025')

    def test_event_name_already_in_artist_database_does_not_win(self):
        # The mistake feeds itself: once "Thunderdome 2025" is a known artist the
        # single dash rule matches it exactly and keeps picking the wrong side.
        self._apply_rule(
            'Thunderdome 2025 ｜ Akimbo vs. Barber', known_artists=['Akimbo', 'Barber', 'Thunderdome 2025']
        )
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Akimbo;Barber')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Thunderdome 2025')

    def test_ascii_pipe_and_dash_separators_behave_the_same(self):
        for title in ['Thunderdome 2025 | Akimbo vs. Barber', 'Thunderdome 2025 - Akimbo vs. Barber']:
            self._apply_rule(title)
            self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Akimbo;Barber')

    def test_festival_without_a_year_is_recognised_by_the_helper(self):
        self.mock_festival_helper.get.side_effect = lambda text, **kwargs: (
            {'festival': 'Thunderdome'} if text.strip() == 'Thunderdome' else None
        )
        self._apply_rule('Thunderdome ｜ Akimbo vs. Barber')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'Akimbo;Barber')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Thunderdome')

    def test_stage_on_the_right_is_not_an_artist(self):
        self._apply_rule('Decibel outdoor 2023 ｜ Mainstage')
        self.assertEqual([], self._artist_calls())

    def test_unknown_right_side_without_artist_separator_is_left_alone(self):
        self._apply_rule('Thunderdome 2025 ｜ Tunnel Of Terror')
        self.assertEqual([], self._artist_calls())

    def test_event_on_the_right_is_not_fuzzy_matched_into_an_artist(self):
        # "Thunderdome 2006" scores 0.81 against a plain "Thunderdome", which used
        # to be enough to make the edition the artist of a numbered upload. The
        # other half is still taken -- artist first, event second is the common
        # ordering -- but the edition itself never is.
        self._apply_rule('567482 - Thunderdome 2006', known_artists=['Thunderdome', 'Akimbo'])
        self.assertNotIn('Thunderdome 2006', self._artist_calls())

    def test_artist_first_title_second_is_untouched(self):
        self._apply_rule('D-Fence - Emporium 2025')
        self.song.tag_collection.set_item.assert_any_call(ARTIST, 'D-Fence')
        self.song.tag_collection.set_item.assert_any_call(TITLE, 'Emporium 2025')


class DisplayArtistCandidateTest(unittest.TestCase):
    """Which written credit is worth keeping, and which is only the text a name came from.

    Everything here goes through `set_cleaned_artist`, not through the helper it calls:
    the helper on its own cannot show that the rules actually offer it anything, nor that
    they offer it the right segment.

    The candidate is only remembered here. Whether it is written to the file is
    CaptureDisplayArtistRuleTest's subject -- the rules that run after these can still
    add an artist the credit does not name.
    """

    def setUp(self):
        self.song = MagicMock()
        self.song.display_artist_candidate = None
        self.artist_db = MagicMock()
        self.artist_db.get_all_values.return_value = ['Angerfist', 'Miss K8']

    def remembered(self, names, source):
        set_cleaned_artist(self.song, names, self.artist_db, source=source)
        return self.song.display_artist_candidate

    def test_a_credit_that_is_the_artist_list_spelled_differently_is_remembered(self):
        self.assertEqual(
            'Angerfist & Miss K8',
            self.remembered(['Angerfist', 'Miss K8'], 'Angerfist & Miss K8'),
        )

    def test_a_single_artist_is_not_given_a_second_copy_of_its_own_name(self):
        self.assertIsNone(self.remembered(['Angerfist'], 'Angerfist'))

    def test_a_rule_that_knows_no_raw_segment_remembers_nothing(self):
        self.assertIsNone(self.remembered(['Angerfist', 'Miss K8'], None))

    def test_a_name_the_library_rejected_is_not_kept_as_a_credit(self):
        """The fuzzy branches keep only the candidates that matched a known artist.

        `Angerfist & Nobody` yields one artist, so writing the whole segment would put a
        credit on the track for someone the library deliberately refused -- and the web
        player shows the display artist in preference to the artist list.
        """
        self.assertIsNone(self.remembered(['Angerfist'], 'Angerfist & Nobody'))

    def test_an_annotation_stripped_off_a_name_does_not_come_back_as_the_credit(self):
        """`set_cleaned_artist` drops bracketed text and trailing words like "live"."""
        self.assertIsNone(self.remembered(['Angerfist'], 'Angerfist (live)'))
        self.assertIsNone(self.remembered(['Angerfist'], 'Angerfist live'))

    def test_the_segment_the_multi_dash_rule_picked_is_the_one_offered(self):
        """End to end through the rule, so a swapped argument would show up here."""
        song = MagicMock()
        song.display_artist_candidate = None
        song.path = lambda: '/tmp/youtube/Q-dance/track.mp3'
        song.tag_collection.has_item.return_value = False
        title = 'Defqon.1 2025 - Angerfist & Miss K8 - Raise Your Fist'
        song.tag_collection.get_item_as_string.side_effect = lambda key: {
            ARTIST: '',
            TITLE: title,
            ORIGINAL_TITLE: title,
        }[key]
        genres = MagicMock()
        genres.get_all.return_value = []
        ignored = MagicMock()
        ignored.get_all.return_value = []
        InferArtistFromTitleRule(artist_db=self.artist_db, genre_db=genres, ignored_db=ignored).apply(song)
        self.assertEqual('Angerfist & Miss K8', song.display_artist_candidate)


class HasCloseArtistTest(unittest.TestCase):
    """has_close_artist must answer exactly what get_close_matches answered, only sooner."""

    def test_agrees_with_difflib_on_random_names(self):
        rng = random.Random(7)
        alphabet = string.ascii_lowercase + '  '
        names = {''.join(rng.choice(alphabet) for _ in range(rng.randint(3, 12))) for _ in range(400)}
        names |= {'angerfist', 'miss k8', 'motz', 'dr. peacock', 'the freaky bastard'}
        probes = [''.join(rng.choice(alphabet) for _ in range(rng.randint(3, 12))) for _ in range(300)]
        probes += ['angerfist', 'angerfits', 'potz', 'mot', 'miss k', 'dr peacock', 'freaky bastard']
        for cutoff in (0.6, 0.7, 0.75):
            for probe in probes:
                self.assertEqual(
                    has_close_artist(probe, names, cutoff),
                    bool(get_close_matches(probe, names, n=1, cutoff=cutoff)),
                    (probe, cutoff),
                )

    def test_an_exact_hit_needs_no_scan(self):
        class Unscannable(frozenset):
            def __iter__(self):
                raise AssertionError('scanned')

        self.assertTrue(has_close_artist('motz', Unscannable({'motz'}), 0.7))
