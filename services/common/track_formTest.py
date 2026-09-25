import unittest
from datetime import date

from services.common import track_form
from services.common.Helpers.FestivalHelper import Festival, FestivalHelper
from services.common.Helpers.PodcastHelper import PodcastHelper, Show

ROOT = '/mnt/music'
LONG = 3600.0
SHORT = 300.0


def festivals() -> FestivalHelper:
    """Defqon with a 2012 edition, Qlimax with none."""
    helper = FestivalHelper(preload=False)
    helper.set_festivals(
        [
            Festival(name='Defqon.1', aliases=['Defqon', 'Defqon.1'], editions={2012: date(2012, 6, 23)}),
            Festival(name='Qlimax', aliases=['Qlimax'], editions={}),
        ]
    )
    return helper


def podcasts() -> PodcastHelper:
    """One approved show."""
    helper = PodcastHelper(preload=False)
    helper.set_shows([Show(name='Hard With Style', aliases=['Hard With Style', 'HWS'])])
    return helper


def form(path, duration=LONG, title=''):
    return track_form.derive_form(path, ROOT, duration, title, festivals(), podcasts())


class DeriveFormTest(unittest.TestCase):
    def test_unknown_length_has_no_form(self):
        self.assertIsNone(form(f'{ROOT}/Livesets/x/a.mp3', duration=None))
        self.assertIsNone(form(f'{ROOT}/Livesets/x/a.mp3', duration=0))

    def test_a_short_file_is_a_track_wherever_it_sits(self):
        # The short files under Podcasts/ are the unmixed tracks of a Top 40.
        self.assertEqual(form(f'{ROOT}/Podcasts/Hardstyle top 40/2012/01-a.mp3', duration=SHORT), 'track')
        self.assertEqual(form(f'{ROOT}/Livesets/Defqon.1 2012/a.mp3', duration=SHORT), 'track')
        self.assertEqual(form(f'{ROOT}/Top 100/2012/a.mp3', duration=SHORT), 'track')

    def test_the_liveset_and_telegram_folders_hold_livesets(self):
        self.assertEqual(form(f'{ROOT}/Livesets/Someone/a.mp3'), 'liveset')
        self.assertEqual(form(f'{ROOT}/Telegram/rips/a.mp3'), 'liveset')

    def test_the_podcast_folder_holds_podcasts(self):
        self.assertEqual(form(f'{ROOT}/Podcasts/The Magic Show/2011/week 023.mp3'), 'podcast')

    def test_folder_names_are_case_insensitive(self):
        self.assertEqual(form(f'{ROOT}/livesets/x/a.mp3'), 'liveset')

    def test_a_known_show_makes_a_download_a_podcast(self):
        self.assertEqual(form(f'{ROOT}/Soundcloud/Someone/a.mp3', title='Hard With Style Episode 120'), 'podcast')

    def test_a_festival_in_the_title_makes_a_download_a_liveset(self):
        self.assertEqual(form(f'{ROOT}/Youtube/Q-dance/a.mp3', title='Headhunterz @ Defqon.1 2012'), 'liveset')

    def test_a_festival_in_the_path_needs_a_year(self):
        self.assertEqual(form(f'{ROOT}/Soundcloud/Qlimax 2019/a.mp3', title='Set'), 'liveset')
        self.assertEqual(form(f'{ROOT}/Soundcloud/Qlimax/a.mp3', title='Set'), 'set')

    def test_a_podcast_beats_a_festival(self):
        self.assertEqual(form(f'{ROOT}/Soundcloud/x/a.mp3', title='HWS 12 - live from Defqon.1 2012'), 'podcast')

    def test_anything_else_long_is_a_set(self):
        self.assertEqual(form(f'{ROOT}/Warm Up Mixes/a.mp3'), 'set')
        self.assertEqual(form(f'{ROOT}/EPs/Label/CAT001/01 continuous mix.flac'), 'set')
        self.assertEqual(form(f'{ROOT}/Soundcloud/dj/yearmix.mp3', title='Yearmix 2012'), 'set')

    def test_a_path_outside_the_root_uses_no_folder_rule(self):
        self.assertEqual(track_form.derive_form('/elsewhere/Livesets/x/a.mp3', ROOT, LONG, 'x'), 'set')

    def test_without_helpers_only_length_and_folder_decide(self):
        self.assertEqual(track_form.derive_form(f'{ROOT}/Soundcloud/x/a.mp3', ROOT, LONG, 'Defqon.1 2012'), 'set')


class DerivePerformanceDateTest(unittest.TestCase):
    def test_a_liveset_with_a_known_edition_gets_its_date(self):
        result = track_form.classify(
            f'{ROOT}/Youtube/Q-dance/a.mp3', ROOT, LONG, 'Headhunterz @ Defqon.1 2012', festivals(), podcasts()
        )
        self.assertEqual(result, ('liveset', '2012-06-23'))

    def test_the_path_supplies_festival_and_year_when_the_title_does_not(self):
        result = track_form.classify(
            f'{ROOT}/Livesets/Defqon.1 2012/Brennan Heart.mp3', ROOT, LONG, 'Brennan Heart', festivals(), podcasts()
        )
        self.assertEqual(result, ('liveset', '2012-06-23'))

    def test_no_edition_for_the_year_means_no_date(self):
        result = track_form.classify(f'{ROOT}/Livesets/x/a.mp3', ROOT, LONG, 'Defqon.1 2013', festivals(), podcasts())
        self.assertEqual(result, ('liveset', None))

    def test_a_festival_without_editions_gives_no_date(self):
        self.assertIsNone(track_form.derive_performance_date('liveset', '/x/a.mp3', 'Qlimax 2019', festivals()))

    def test_only_a_liveset_has_a_performance_date(self):
        # A short festival anthem names the festival and year too.
        result = track_form.classify(
            f'{ROOT}/EPs/x/y/a.mp3', ROOT, SHORT, 'Defqon.1 2012 Anthem', festivals(), podcasts()
        )
        self.assertEqual(result, ('track', None))
        self.assertIsNone(track_form.derive_performance_date('set', '/x', 'Defqon.1 2012', festivals()))

    def test_a_liveset_without_a_festival_has_no_date(self):
        self.assertIsNone(track_form.derive_performance_date('liveset', f'{ROOT}/Telegram/x/a.mp3', 'rip', festivals()))


if __name__ == '__main__':
    unittest.main()
