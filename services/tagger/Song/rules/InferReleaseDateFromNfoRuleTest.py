import unittest
from datetime import date
from unittest.mock import MagicMock, patch

from services.common.store_lookup import NOT_FOUND, OK, StoreAlbum
from services.tagger.constants import BARCODE, DATE, DATE_SOURCE, ORIGINAL_DATE
from services.tagger.Song.rules.InferReleaseDateFromNfoRule import InferReleaseDateFromNfoRule

MINUS_MILITIA_DIR = (
    '/music/EPs/B2S/Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)'
    '-SINGLE-WEB-2026-UTNG'
)
# The .nfo of that release as it reads on production, two columns to a line.
MINUS_MILITIA_NFO = """
       Rip.date: 01.10.2026                Year....: 2026
       Company.: B2S                       Length..: 03:24
       Rls.type: WEB                       Tracks..: 01
       Genre...: Techno                    Size....: 7.78 MB

       Url:https://deezer.com/album/1104265012
"""
DEEZER_ALBUM = StoreAlbum('deezer', '1104265012', OK, 'b2s Records', '8719244873593', '2026-10-02', 'Recover')


class FakeStore:
    """A store cache that answers from a dict and never touches the network."""

    def __init__(self, albums=None):
        self.albums = albums or {}
        self.asked = []

    def lookup(self, link, budget=None):
        self.asked.append((link.store, link.album_id, budget))
        return self.albums.get(link.album_id)


class RuleCase(unittest.TestCase):
    """A song double, a scene-group helper and a fake store; no file, database or network."""

    def setUp(self):
        self.song = MagicMock()
        self.song.arrival_date = None
        self.song.path = MagicMock(return_value='/music/EPs/008 Recordings/X_-_Y-(008R017)-WEB-2026-ZzZz/01-x.mp3')
        self.tags = {}
        self.song.tag_collection.get_item_as_string = MagicMock(side_effect=lambda tag: self.tags.get(tag, ''))
        self.song.tag_collection.set_item = MagicMock(side_effect=self.tags.__setitem__)
        self.helper = MagicMock()
        self.helper.get = MagicMock(return_value=[])
        self.store = FakeStore()

    def _apply(self, nfo_text):
        rule = InferReleaseDateFromNfoRule(format_helper=self.helper, store=self.store)
        with patch('services.tagger.Song.rules.InferReleaseDateFromNfoRule.NfoDate.read_nfo', return_value=nfo_text):
            rule.apply(self.song)

    def written(self):
        return {call.args[0]: call.args[1] for call in self.song.tag_collection.set_item.call_args_list}


class InferReleaseDateFromNfoRuleTest(RuleCase):
    def test_writes_the_street_date_at_day_precision(self):
        self._apply('Str.date : 16-01-2026')
        self.assertEqual({ORIGINAL_DATE: '2026-01-16', DATE_SOURCE: 'nfo-street'}, self.written())

    def test_a_store_date_line_counts_as_a_release_date(self):
        self._apply('Store date : 16-01-2026')
        self.assertEqual({ORIGINAL_DATE: '2026-01-16', DATE_SOURCE: 'nfo-release'}, self.written())

    def test_consults_the_override_table_for_the_scene_group(self):
        self.helper.get = MagicMock(return_value=['md'])
        self._apply('Releasedate : 05.06.2026')
        self.helper.get.assert_called_once_with('ZzZz')
        self.assertEqual('2026-05-06', self.written()[ORIGINAL_DATE])

    def test_reads_the_dot_padded_date_line_of_aov_int_month_first(self):
        self.song.path = MagicMock(
            return_value='/music/EPs/Roughstate/ROUGH247PRO - Rejecta-Living_My_Dream-()-WEB-2022-AOV_INT/01-x.mp3'
        )
        self.helper.get = MagicMock(return_value=['md'])
        self._apply('Genre.........: Techno\nDate..........: 11.23.2022\nEncoder.......: LAME 3.100\n')
        self.helper.get.assert_called_once_with('AOV_INT')
        self.assertEqual({ORIGINAL_DATE: '2022-11-23', DATE_SOURCE: 'nfo-rip'}, self.written())

    def test_leaves_a_full_date_of_unknown_origin_alone(self):
        self.tags[ORIGINAL_DATE] = '2026-01-02'
        self._apply('Str.date : 16-01-2026')
        self.song.tag_collection.set_item.assert_not_called()

    def test_upgrades_a_year_only_value(self):
        self.tags[ORIGINAL_DATE] = '2026'
        self._apply('Str.date : 16-01-2026')
        self.assertEqual('2026-01-16', self.written()[ORIGINAL_DATE])

    def test_falls_back_to_a_day_precision_date_tag(self):
        self.tags[DATE] = '20260116'
        self._apply(None)
        self.assertEqual({ORIGINAL_DATE: '2026-01-16', DATE_SOURCE: 'tag'}, self.written())

    def test_a_year_only_date_tag_is_not_a_fallback(self):
        self.tags[DATE] = '2026'
        self._apply(None)
        self.song.tag_collection.set_item.assert_not_called()

    def test_writes_nothing_when_there_is_no_evidence(self):
        self._apply('no dates in here')
        self.song.tag_collection.set_item.assert_not_called()


class DateLadderTest(RuleCase):
    """The Minus Militia release of 2026-10-02, rung by rung."""

    def setUp(self):
        super().setUp()
        self.song.path = MagicMock(return_value=MINUS_MILITIA_DIR + '/01-minus_militia_and_nolz_-_recover.mp3')
        self.tags[DATE] = '2026'

    def test_the_deezer_date_wins_and_the_upc_becomes_the_barcode(self):
        self.store.albums['1104265012'] = DEEZER_ALBUM
        self._apply(MINUS_MILITIA_NFO)
        self.assertEqual(
            {BARCODE: '8719244873593', ORIGINAL_DATE: '2026-10-02', DATE_SOURCE: 'deezer'},
            self.written(),
        )
        # Cache only: the tagger never asks the network (no budget).
        self.assertEqual([('deezer', '1104265012', None)], self.store.asked)

    def test_without_the_store_the_rip_date_is_used_and_marked_as_such(self):
        self._apply(MINUS_MILITIA_NFO)
        self.assertEqual({ORIGINAL_DATE: '2026-10-01', DATE_SOURCE: 'nfo-rip'}, self.written())

    def test_a_gone_album_is_skipped(self):
        self.store.albums['1104265012'] = StoreAlbum('deezer', '1104265012', NOT_FOUND)
        self._apply(MINUS_MILITIA_NFO)
        self.assertEqual('nfo-rip', self.written()[DATE_SOURCE])

    def test_a_store_date_from_another_year_is_not_trusted(self):
        self.store.albums['1104265012'] = StoreAlbum('deezer', '1104265012', OK, release_date='2019-03-01')
        self._apply(MINUS_MILITIA_NFO)
        self.assertEqual({ORIGINAL_DATE: '2026-10-01', DATE_SOURCE: 'nfo-rip'}, self.written())

    def test_a_rip_date_is_upgraded_once_the_store_answer_is_cached(self):
        self.tags[ORIGINAL_DATE] = '2026-10-01'
        self.tags[DATE_SOURCE] = 'nfo-rip'
        self.store.albums['1104265012'] = DEEZER_ALBUM
        self._apply(MINUS_MILITIA_NFO)
        self.assertEqual('2026-10-02', self.written()[ORIGINAL_DATE])
        self.assertEqual('deezer', self.written()[DATE_SOURCE])

    def test_a_backfill_retag_lifts_a_rip_date_beside_a_full_file_date(self):
        # What the backfill queues: the file already has full dates everywhere, the retag
        # carries no arrival date, and the Deezer answer is in the cache by now.
        self.song.path = MagicMock(return_value=f'{MINUS_MILITIA_DIR}/01-minus_militia.mp3')
        self.tags.update({DATE: '2026-10-01', ORIGINAL_DATE: '2026-10-01', DATE_SOURCE: 'nfo-rip'})
        self.store.albums['1104265012'] = DEEZER_ALBUM
        self._apply(MINUS_MILITIA_NFO)
        self.assertEqual('2026-10-02', self.tags[ORIGINAL_DATE])
        self.assertEqual('deezer', self.tags[DATE_SOURCE])

    def test_an_arrival_date_is_lifted_to_the_store_date_on_a_retag(self):
        self.tags.update({ORIGINAL_DATE: '2026-10-05', DATE_SOURCE: 'arrival'})
        self.store.albums['1104265012'] = DEEZER_ALBUM
        self._apply(MINUS_MILITIA_NFO)
        self.assertEqual('2026-10-02', self.tags[ORIGINAL_DATE])
        self.assertEqual('deezer', self.tags[DATE_SOURCE])

    def test_an_arrival_date_stays_when_a_retag_finds_nothing_better(self):
        self.tags.update({ORIGINAL_DATE: '2026-10-05', DATE_SOURCE: 'arrival'})
        self._apply('nothing dated, no link')
        self.song.tag_collection.set_item.assert_not_called()

    def test_a_pre_ladder_nfo_date_is_lifted_to_the_store_date(self):
        # Before the ladder this rule wrote the .nfo date without DATE_SOURCE (4.141 files on
        # production were skipped as "a person's date" for that reason).
        self.tags[ORIGINAL_DATE] = '2026-10-01'
        self.store.albums['1104265012'] = DEEZER_ALBUM
        self._apply(MINUS_MILITIA_NFO)
        self.assertEqual('2026-10-02', self.tags[ORIGINAL_DATE])
        self.assertEqual('deezer', self.tags[DATE_SOURCE])

    def test_a_pre_ladder_nfo_date_that_is_still_the_best_only_gets_its_source(self):
        self.tags[ORIGINAL_DATE] = '2026-01-16'
        self._apply('Str.date : 16-01-2026')
        self.assertEqual({DATE_SOURCE: 'nfo-street'}, self.written())

    def test_a_pre_ladder_date_from_the_file_date_counts_as_tag(self):
        self.tags.update({DATE: '2026-03-04', ORIGINAL_DATE: '2026-03-04'})
        self.store.albums['1104265012'] = DEEZER_ALBUM
        self._apply(MINUS_MILITIA_NFO)
        self.assertEqual(
            {ORIGINAL_DATE: '2026-10-02', DATE_SOURCE: 'deezer'},
            {ORIGINAL_DATE: self.tags[ORIGINAL_DATE], DATE_SOURCE: self.tags[DATE_SOURCE]},
        )

    def test_a_store_date_is_never_downgraded(self):
        self.tags[ORIGINAL_DATE] = '2026-10-02'
        self.tags[DATE_SOURCE] = 'deezer'
        self.tags[BARCODE] = '8719244873593'
        self._apply(MINUS_MILITIA_NFO)
        self.song.tag_collection.set_item.assert_not_called()

    def test_the_arrival_date_is_the_last_rung_before_the_year(self):
        self.song.arrival_date = date(2026, 10, 2)
        self._apply('nothing dated, no link')
        self.assertEqual({ORIGINAL_DATE: '2026-10-02', DATE_SOURCE: 'arrival'}, self.written())

    def test_an_arrival_in_another_year_is_not_a_release_date(self):
        self.song.arrival_date = date(2027, 1, 3)
        self._apply('nothing dated, no link')
        self.song.tag_collection.set_item.assert_not_called()

    def test_a_rip_date_beats_the_arrival_date(self):
        self.song.arrival_date = date(2026, 10, 2)
        self._apply(MINUS_MILITIA_NFO)
        self.assertEqual('nfo-rip', self.written()[DATE_SOURCE])

    def test_a_retag_with_the_same_answer_writes_nothing(self):
        self.tags[ORIGINAL_DATE] = '2026-10-01'
        self.tags[DATE_SOURCE] = 'nfo-rip'
        self._apply(MINUS_MILITIA_NFO)
        self.song.tag_collection.set_item.assert_not_called()


if __name__ == '__main__':
    unittest.main()
