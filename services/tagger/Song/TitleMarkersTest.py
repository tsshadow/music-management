"""Release, series and channel markers, on the real production titles of bug report 142."""

import unittest
from unittest.mock import MagicMock

from services.tagger.constants import ALBUM, ARTIST, CATALOG_NUMBER, ORIGINAL_TITLE, TITLE
from services.tagger.Song.rules.InferArtistFromTitleRule import InferArtistFromTitleRule
from services.tagger.Song.rules.InferFeatureFromTitleRule import InferFeatureFromTitleRule
from services.tagger.Song.title_markers import is_channel_name, parse_title_markers


class ParseTitleMarkersTest(unittest.TestCase):
    """The pure parser: what is left to split, and what the marker said."""

    def test_pipe_presents_series_is_stripped_to_the_album(self):
        markers = parse_title_markers('Luner - Holding On To You ｜ Q-dance presents SPEQTRUM')
        self.assertEqual(markers.title, 'Luner - Holding On To You')
        self.assertEqual(markers.album, 'SPEQTRUM')

    def test_bracket_presents_release(self):
        markers = parse_title_markers('Deviouz & Matzic - Tomorrow (Gearbox Presents Lockdown 3.0)')
        self.assertEqual((markers.title, markers.album), ('Deviouz & Matzic - Tomorrow', 'Lockdown 3.0'))

    def test_square_bracket_presents_with_fullwidth_colon_and_catalogue(self):
        markers = parse_title_markers('YunKe & MBK - You Dont Scare Me [DRS Presents： TSR Album 8.0 - TSR042]')
        self.assertEqual(markers.title, 'YunKe & MBK - You Dont Scare Me')
        self.assertEqual((markers.album, markers.catalog), ('TSR Album 8.0', 'TSR042'))

    def test_square_bracket_presents_without_colon(self):
        markers = parse_title_markers('YunKe & MBK - You Dont Scare Me [DRS Presents TSR ALBUM 8.0 - TSR042]')
        self.assertEqual((markers.album, markers.catalog), ('TSR ALBUM 8.0', 'TSR042'))

    def test_colon_bracket_naming_an_album(self):
        markers = parse_title_markers('Krowdexx - Fastlane (Dungeon： The Mini Album)')
        self.assertEqual((markers.title, markers.album), ('Krowdexx - Fastlane', 'Dungeon: The Mini Album'))

    def test_colon_bracket_without_a_release_word_stays(self):
        markers = parse_title_markers('Artist - Song (Intro: Part 2)')
        self.assertEqual(markers.title, 'Artist - Song (Intro: Part 2)')
        self.assertIsNone(markers.album)

    def test_a_remix_bracket_is_not_a_release(self):
        title = 'LNY TNZ & Ruthless - Fired Up Ft. The Kemist (Kayzo Remix)'
        self.assertEqual(parse_title_markers(title).title, title)

    def test_leading_presents_is_left_to_the_artist_rule(self):
        title = 'Bloodlust presents: The Assassination | Decibel outdoor 2024 | Mainstage | SAVAGE SUNDAY'
        markers = parse_title_markers(title)
        self.assertEqual(markers.title, title)
        self.assertIsNone(markers.artist)

    def test_trailing_channel_segment_is_dropped(self):
        markers = parse_title_markers('KAASCOUSE ｜ The Next MC - Optreden ｜ 101Barz', ['101Barz'])
        self.assertEqual(markers.title, 'KAASCOUSE ｜ The Next MC - Optreden')

    def test_channel_series_after_an_artist_title_goes_too(self):
        markers = parse_title_markers('Jimmy Huru - #BPMJIMMYHURU ｜ BPM ｜ 101BARZ', ['101Barz'])
        self.assertEqual(markers.title, 'Jimmy Huru - #BPMJIMMYHURU')

    def test_a_segment_that_is_not_the_channel_stays(self):
        title = 'Warface & Rooler @ Defqon.1 2025 ｜ The Gathering ｜ Blue Stage'
        self.assertEqual(parse_title_markers(title, ['Q-dance']).title, title)

    def test_interview(self):
        markers = parse_title_markers('QAPITAL 2019 ｜ Interview with Rejecta')
        self.assertEqual((markers.artist, markers.final_title), ('Rejecta', 'QAPITAL 2019 Interview'))

    def test_preview_takes_the_artist_from_the_last_segment(self):
        markers = parse_title_markers('Qlimax 2010 ｜ Blu-ray ⧸ DVD Preview ｜ Zatox')
        self.assertEqual((markers.artist, markers.final_title), ('Zatox', 'Qlimax 2010 - Blu-ray ⧸ DVD Preview'))

    def test_cover(self):
        markers = parse_title_markers("Bowser's Castle (Mario Kart World) ｜ Cover by Gabocarina96")
        self.assertEqual(
            (markers.artist, markers.final_title), ('Gabocarina96', "Bowser's Castle (Mario Kart World) (Cover)")
        )

    def test_channel_name_comparison_ignores_case_and_punctuation(self):
        self.assertTrue(is_channel_name('101BARZ', ['101Barz']))
        self.assertTrue(is_channel_name('Q-Dance', ['Q-dance']))
        self.assertFalse(is_channel_name('BPM', ['101Barz']))


class FakeTags:
    """A dict-backed stand-in for TagCollection: enough for the rules under test."""

    def __init__(self, values):
        self.values = dict(values)

    def get_item_as_string(self, key):
        return self.values.get(key, '')

    def set_item(self, key, value):
        self.values[key] = value

    def has_item(self, key):
        return bool(self.values.get(key))


class FakeSong:
    """A download with a channel, for the rule as SoundcloudSong/YoutubeSong runs it."""

    def __init__(self, title, album='Youtube (Q-dance)', channel=('Q-dance', 'Q-dance'), extra=None):
        self.tag_collection = FakeTags({TITLE: title, ALBUM: album, **(extra or {})})
        self._channel = list(channel)

    def channel_stand_ins(self):
        return self._channel

    def path(self):
        return f'/music/Youtube/{self._channel[0]}/track.m4a'


class InferArtistFromReleaseMarkerTest(unittest.TestCase):
    """The whole rule over the bug-report titles: artist, title and album."""

    def setUp(self):
        self.artist_db = MagicMock()
        self.artist_db.get_all_values.return_value = [
            'Q-dance',
            'Gearbox',
            'DRS',
            'Dungeon',
            '101Barz',
            'Interview',
            'Luner',
            'Deviouz',
            'Krowdexx',
        ]
        self.genres_db = MagicMock()
        self.genres_db.get_all.return_value = ['Hardstyle']
        self.ignored_db = MagicMock()
        self.ignored_db.get_all.return_value = []

    def _tag(self, song):
        rule = InferArtistFromTitleRule(
            artist_db=self.artist_db, genre_db=self.genres_db, ignored_db=self.ignored_db, festival_helper=None
        )
        rule.apply(song)
        return song.tag_collection.values

    def test_q_dance_series(self):
        tags = self._tag(FakeSong('Luner - Holding On To You ｜ Q-dance presents SPEQTRUM'))
        self.assertEqual((tags[ARTIST], tags[TITLE], tags[ALBUM]), ('Luner', 'Holding On To You', 'SPEQTRUM'))

    def test_gearbox_release(self):
        song = FakeSong('Deviouz & Matzic - Tomorrow (Gearbox Presents Lockdown 3.0)', album='Soundcloud (Gearbox)')
        tags = self._tag(song)
        self.assertEqual((tags[ARTIST], tags[TITLE], tags[ALBUM]), ('Deviouz;Matzic', 'Tomorrow', 'Lockdown 3.0'))

    def test_drs_release_sets_the_catalogue_number(self):
        tags = self._tag(FakeSong('YunKe & MBK - You Dont Scare Me [DRS Presents： TSR Album 8.0 - TSR042]'))
        self.assertEqual(tags[TITLE], 'You Dont Scare Me')
        self.assertEqual((tags[ALBUM], tags[CATALOG_NUMBER]), ('TSR Album 8.0', 'TSR042'))
        self.assertNotIn('DRS', tags[ARTIST])

    def test_a_catalogue_number_already_on_the_file_stays(self):
        song = FakeSong(
            'YunKe & MBK - You Dont Scare Me [DRS Presents TSR ALBUM 8.0 - TSR042]', extra={CATALOG_NUMBER: 'X1'}
        )
        self.assertEqual(self._tag(song)[CATALOG_NUMBER], 'X1')

    def test_mini_album(self):
        tags = self._tag(FakeSong('Krowdexx - Fastlane (Dungeon： The Mini Album)'))
        self.assertEqual((tags[ARTIST], tags[TITLE], tags[ALBUM]), ('Krowdexx', 'Fastlane', 'Dungeon: The Mini Album'))

    def test_a_hand_set_album_is_never_overwritten(self):
        song = FakeSong('Luner - Holding On To You ｜ Q-dance presents SPEQTRUM', album='My Favourites')
        self.assertEqual(self._tag(song)[ALBUM], 'My Favourites')

    def test_a_retag_replaces_the_title_an_earlier_pass_read_out_of_the_marker(self):
        song = FakeSong(
            'Luner - Holding On To You ｜ Q-dance presents SPEQTRUM',
            extra={ORIGINAL_TITLE: 'Luner - Holding On To You ｜ Q-dance presents SPEQTRUM', ARTIST: 'Q-dance'},
        )
        song.tag_collection.values[TITLE] = 'SPEQTRUM'
        tags = self._tag(song)
        self.assertEqual((tags[ARTIST], tags[TITLE], tags[ALBUM]), ('Luner', 'Holding On To You', 'SPEQTRUM'))

    def test_101barz_channel_is_not_the_artist(self):
        song = FakeSong('KAASCOUSE ｜ The Next MC - Optreden ｜ 101Barz', channel=('101Barz', '101Barz'))
        tags = self._tag(song)
        self.assertEqual((tags[ARTIST], tags[TITLE]), ('KAASCOUSE', 'The Next MC - Optreden'))

    def test_101barz_series(self):
        song = FakeSong('Jimmy Huru - #BPMJIMMYHURU ｜ BPM ｜ 101BARZ', channel=('101Barz', '101Barz'))
        tags = self._tag(song)
        self.assertEqual((tags[ARTIST], tags[TITLE]), ('Jimmy Huru', '#BPMJIMMYHURU'))

    def test_interview(self):
        tags = self._tag(FakeSong('QAPITAL 2019 ｜ Interview with Rejecta'))
        self.assertEqual((tags[ARTIST], tags[TITLE]), ('Rejecta', 'QAPITAL 2019 Interview'))

    def test_preview(self):
        tags = self._tag(FakeSong('Qlimax 2010 ｜ Blu-ray ⧸ DVD Preview ｜ Zatox'))
        self.assertEqual((tags[ARTIST], tags[TITLE]), ('Zatox', 'Qlimax 2010 - Blu-ray ⧸ DVD Preview'))

    def test_cover(self):
        tags = self._tag(FakeSong("Bowser's Castle (Mario Kart World) ｜ Cover by Gabocarina96"))
        self.assertEqual((tags[ARTIST], tags[TITLE]), ('Gabocarina96', "Bowser's Castle (Mario Kart World) (Cover)"))

    def test_a_title_without_markers_keeps_the_channel_album(self):
        tags = self._tag(FakeSong('Luner - Holding On To You'))
        self.assertEqual(tags[ALBUM], 'Youtube (Q-dance)')


class FeatureKeepsTheRemixTest(unittest.TestCase):
    """A featured artist is read without swallowing the remix bracket behind it."""

    def _apply(self, title):
        artist_tag = MagicMock()
        artist_tag.to_array.return_value = ['LNY TNZ', 'Ruthless']
        song = MagicMock()
        song.tag_collection.get_item_as_string.return_value = title
        song.tag_collection.get_item.return_value = artist_tag
        InferFeatureFromTitleRule().apply(song)
        return song, artist_tag

    def test_remix_bracket_stays_in_the_title(self):
        song, artist_tag = self._apply('Fired Up Ft. The Kemist (Kayzo Remix)')
        song.tag_collection.set_item.assert_called_once_with(TITLE, 'Fired Up (Kayzo Remix)')
        artist_tag.add.assert_called_once_with('The Kemist')

    def test_unbracketed_feature_at_the_end(self):
        song, artist_tag = self._apply('Fired Up feat. The Kemist')
        song.tag_collection.set_item.assert_called_once_with(TITLE, 'Fired Up')

    def test_bracketed_feature(self):
        song, _ = self._apply('Fired Up (feat. The Kemist) (Kayzo Remix)')
        song.tag_collection.set_item.assert_called_once_with(TITLE, 'Fired Up (Kayzo Remix)')


if __name__ == '__main__':
    unittest.main()
