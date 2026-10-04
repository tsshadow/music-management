import unittest
from datetime import date

from services.common import track_form
from services.common.Helpers.FestivalHelper import Festival, FestivalHelper
from services.common.Helpers.PodcastHelper import PodcastHelper, Show

ROOT = '/mnt/music'
LONG = 3600.0
SHORT = 300.0


def festivals() -> FestivalHelper:
    """Defqon with a 2012 edition, Qlimax and Decibel with none."""
    helper = FestivalHelper(preload=False)
    helper.set_festivals(
        [
            Festival(name='Defqon.1', aliases=['Defqon', 'Defqon.1'], editions={2012: date(2012, 6, 23)}),
            Festival(name='Qlimax', aliases=['Qlimax'], editions={}),
            Festival(name='Decibel Outdoor', aliases=['Decibel Outdoor', 'Decibel'], editions={}),
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

    def test_a_festival_in_a_label_track_title_does_not_make_it_a_liveset(self):
        # Issue #76 / bug report 109: a 13.5-minute EP track whose title contains "Decibel".
        path = f'{ROOT}/EPs/Karnage Records/KRG_003-RE - Radium_-_Karnage_03_(remastered)-()-WEB-2021/01_radium_-_decibel_dictature.mp3'
        self.assertEqual(form(path, duration=810.0, title='Decibel Dictature'), 'set')

    def test_a_labels_festival_mix_album_is_a_set(self):
        path = f'{ROOT}/EPs/QDance/QCD010 - Defqon (2015)/23_va_-_defqon.1_2015_mix_1_(mixed_by_ran-d).mp3'
        self.assertEqual(form(path, title='Defqon.1 2015 Mix 1 (Mixed by Ran-D)'), 'set')

    def test_a_live_recording_in_the_label_tree_stays_a_liveset(self):
        dvd = f'{ROOT}/EPs/TOFF Music/TOFF006 VA_-_Reverze_Creation_Of_Live-DVD-2009-HB/103_coone.mp3'
        self.assertEqual(form(dvd, duration=720.0, title='Live @ Defqon.1 2012'), 'liveset')
        self.assertEqual(
            form(f'{ROOT}/EPs/QDance/VA-Qlimax_2005-DVD-2006-DDS/04-qlimax_2005-zany.mp3', title='Zany'), 'liveset'
        )
        stream = f'{ROOT}/EPs/__TODO/ - Q-Base_2010-Tha_Playah_Live-STREAM-09-11-2010/01.mp3'
        self.assertEqual(form(stream, title='Qlimax 2010 Tha Playah'), 'liveset')

    def test_a_live_word_needs_a_festival_too(self):
        self.assertEqual(form(f'{ROOT}/EPs/Label/CAT001 - Live Album/01.mp3', title='Live Forever'), 'set')

    def test_live_only_counts_as_a_whole_word(self):
        path = f'{ROOT}/EPs/Label/CAT002 - Oliver-WEB-2012/01-delivery.mp3'
        self.assertEqual(form(path, title='Decibel Delivery'), 'set')

    def test_a_festival_named_track_outside_the_label_tree_is_still_a_liveset(self):
        self.assertEqual(form(f'{ROOT}/Soundcloud/Radium/a.mp3', title='Decibel Dictature'), 'liveset')
        self.assertEqual(form(f'{ROOT}/Youtube/Q-dance/a.mp3', title='Decibel Outdoor 2019 | Warface'), 'liveset')

    def test_a_label_mix_album_loses_its_performance_date(self):
        path = f'{ROOT}/EPs/B2S/Defqon 2012/01-mix.mp3'
        self.assertEqual(
            track_form.classify(path, ROOT, LONG, 'Defqon.1 2012 Mix 1', festivals(), podcasts()), ('set', None)
        )
        live = f'{ROOT}/EPs/B2S/Defqon 2012 DVD/01-live.mp3'
        self.assertEqual(
            track_form.classify(live, ROOT, LONG, 'Live at Defqon.1 2012', festivals(), podcasts()),
            ('liveset', '2012-06-23'),
        )

    def test_a_path_outside_the_root_uses_no_folder_rule(self):
        self.assertEqual(track_form.derive_form('/elsewhere/Livesets/x/a.mp3', ROOT, LONG, 'x'), 'set')

    def test_without_helpers_only_length_and_folder_decide(self):
        self.assertEqual(track_form.derive_form(f'{ROOT}/Soundcloud/x/a.mp3', ROOT, LONG, 'Defqon.1 2012'), 'set')


class NonMusicFormTest(unittest.TestCase):
    """Interviews and DVD previews among the downloads (docs/designs/non-music-forms/)."""

    def test_production_interviews_are_interviews(self):
        for path, title in [
            ('Youtube/Ground Zero Festival', 'Ground Zero Festival 2014 - Lenny Dee Interview'),
            ('Youtube/Q-dance', 'QAPITAL 2019 Interview'),
            ('Youtube/Q-dance', 'QAPITAL 2019 ｜ Interview with Rejecta'),
            ('Youtube/DJ Mag', 'Top 100 DJs Profile Interview (2014)'),
            ('Youtube/101Barz', "'Ik houd echt van Rotterdam' - Interview"),
            ('Youtube/Supremacy', 'MINUS MILITIA INTERVIEW SUPREMACY'),
            ('Soundcloud/Someone', 'Interviews Dano & Joey Beltram Fun Factory 1992'),
        ]:
            with self.subTest(title=title):
                self.assertEqual(form(f'{ROOT}/{path}/a.mp3', duration=SHORT, title=title), 'interview')

    def test_production_dvd_previews_are_previews(self):
        for title in [
            'DVD Preview',
            'Blu-ray;DVD Preview',
            'DVD;Bluray preview',
            'Q-dance DVD preview',
            'Qlimax 2010 ｜ Blu-ray ⧸ DVD Preview ｜ Zatox',
            'Preview DVD',
        ]:
            with self.subTest(title=title):
                self.assertEqual(form(f'{ROOT}/Youtube/Q-dance/a.mp3', duration=SHORT, title=title), 'preview')

    def test_the_title_decides_before_the_length(self):
        # A 35-minute DVD preview and a 12-minute interview are still talk, not a set or live set.
        self.assertEqual(form(f'{ROOT}/Youtube/Q-dance/a.mp3', duration=2122.0, title='Q-dance DVD preview'), 'preview')
        self.assertEqual(form(f'{ROOT}/Youtube/101Barz/a.mp3', duration=720.0, title='The Interview'), 'interview')
        self.assertEqual(form(f'{ROOT}/Telegram/rips/a.mp3', title='Qlimax DVD Preview'), 'preview')

    def test_a_non_music_title_needs_no_duration(self):
        self.assertEqual(form(f'{ROOT}/Youtube/Q-dance/a.mp3', duration=None, title='DVD Preview'), 'preview')

    def test_a_song_preview_stays_music(self):
        for title in [
            'Zudröhnen (Preview)',
            '"TKT" Studio Preview',
            '【Preview】Srav3R',
            'Artist - Song (Official Preview)',
        ]:
            with self.subTest(title=title):
                self.assertEqual(form(f'{ROOT}/Soundcloud/Someone/a.mp3', duration=SHORT, title=title), 'track')

    def test_music_with_some_talk_stays_music(self):
        self.assertEqual(
            form(f'{ROOT}/Soundcloud/Pat B/a.mp3', title='Pat B At Topradio Liveset 14-02-2020 + Interview'), 'set'
        )
        self.assertEqual(
            form(
                f'{ROOT}/Soundcloud/X/a.mp3', duration=SHORT, title='Going To An Interview (Outro Storytelling Audio)'
            ),
            'track',
        )
        self.assertEqual(form(f'{ROOT}/Youtube/X/a.mp3', title='Hardstyle Mix + Interview'), 'set')

    def test_an_interview_outside_the_download_folders_stays_music(self):
        # A label release can be a song called "Interview".
        self.assertEqual(
            form(f'{ROOT}/EPs/Label/CAT001/01 - Interview.mp3', duration=SHORT, title='Interview'), 'track'
        )
        self.assertEqual(form('/elsewhere/Youtube/x/a.mp3', duration=SHORT, title='Interview'), 'track')

    def test_interview_is_a_whole_word(self):
        self.assertEqual(form(f'{ROOT}/Youtube/X/a.mp3', duration=SHORT, title='Interviewed by fate'), 'track')

    def test_trailers_teasers_and_aftermovies_stay_music(self):
        for title in ['Defqon.1 2019 | Official Trailer', 'EP teaser', 'Qlimax 2019 | Official Aftermovie']:
            with self.subTest(title=title):
                self.assertEqual(form(f'{ROOT}/Youtube/Q-dance/a.mp3', duration=SHORT, title=title), 'track')

    def test_non_music_has_no_performance_date(self):
        self.assertEqual(
            track_form.classify(f'{ROOT}/Youtube/Q-dance/a.mp3', ROOT, LONG, 'Defqon.1 2012 DVD Preview', festivals()),
            ('preview', None),
        )

    def test_the_non_music_forms_are_forms(self):
        self.assertEqual(track_form.NON_MUSIC_FORMS, {'interview', 'preview'})
        self.assertTrue(set(track_form.FORMS) >= track_form.NON_MUSIC_FORMS)


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
