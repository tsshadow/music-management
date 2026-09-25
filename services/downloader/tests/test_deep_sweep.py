import os
import tempfile
import unittest
from datetime import datetime, timedelta

import pytest

from services.downloader.deep_sweep import (
    DeepSweepReport,
    FlatTrack,
    ListingFailed,
    ids_in_text_archive,
    list_flat,
    wanted_tracks,
)
from services.downloader.write_offs import WriteOff

pytestmark = pytest.mark.mock_base('yt_dlp')

NOW = datetime(2026, 8, 23, 12, 0, 0)
DAY = timedelta(days=1)
BOUNDS = (60, 21600)


def track(track_id: str) -> FlatTrack:
    return FlatTrack(track_id=track_id, url=f'https://example.test/{track_id}', title=track_id)


class WantedTracksTest(unittest.TestCase):
    def test_a_listing_with_nothing_held_wants_everything(self):
        wanted = wanted_tracks(
            [track('a'), track('b')], held=set(), write_offs={}, retry_days=30, now=NOW, bounds=BOUNDS
        )
        self.assertEqual(['a', 'b'], [t.track_id for t in wanted])

    def test_held_tracks_are_not_wanted(self):
        wanted = wanted_tracks(
            [track('a'), track('b')], held={'a'}, write_offs={}, retry_days=30, now=NOW, bounds=BOUNDS
        )
        self.assertEqual(['b'], [t.track_id for t in wanted])

    def test_a_gap_behind_a_held_track_is_still_wanted(self):
        listing = [track('new'), track('held'), track('gap')]
        wanted = wanted_tracks(listing, held={'held'}, write_offs={}, retry_days=30, now=NOW, bounds=BOUNDS)
        self.assertEqual(['new', 'gap'], [t.track_id for t in wanted])

    def test_the_listing_order_is_kept(self):
        listing = [track('c'), track('b'), track('a')]
        wanted = wanted_tracks(listing, held=set(), write_offs={}, retry_days=30, now=NOW, bounds=BOUNDS)
        self.assertEqual(['c', 'b', 'a'], [t.track_id for t in wanted])

    def test_a_written_off_track_is_not_wanted(self):
        offs = {'a': WriteOff('403', NOW, None, 0)}
        wanted = wanted_tracks([track('a')], held=set(), write_offs=offs, retry_days=30, now=NOW, bounds=BOUNDS)
        self.assertEqual([], wanted)

    def test_a_403_past_its_window_is_wanted_again(self):
        offs = {'a': WriteOff('403', NOW - 31 * DAY, None, 0)}
        wanted = wanted_tracks([track('a')], held=set(), write_offs=offs, retry_days=30, now=NOW, bounds=BOUNDS)
        self.assertEqual(['a'], [t.track_id for t in wanted])

    def test_a_short_track_stays_out_under_the_bounds_that_judged_it(self):
        offs = {'a': WriteOff('too_short', NOW, 30, 0)}
        wanted = wanted_tracks([track('a')], held=set(), write_offs=offs, retry_days=30, now=NOW, bounds=BOUNDS)
        self.assertEqual([], wanted)

    def test_a_short_track_is_wanted_again_once_the_floor_drops(self):
        offs = {'a': WriteOff('too_short', NOW, 30, 0)}
        wanted = wanted_tracks([track('a')], held=set(), write_offs=offs, retry_days=30, now=NOW, bounds=(10, 21600))
        self.assertEqual(['a'], [t.track_id for t in wanted])


class ReportTest(unittest.TestCase):
    def test_a_pass_with_nothing_left_is_complete(self):
        report = DeepSweepReport(listed=10, held=8, written_off=2, wanted=0)
        self.assertTrue(report.complete)

    def test_a_capped_pass_is_not_complete(self):
        report = DeepSweepReport(listed=10, held=5, written_off=0, wanted=5, downloaded=5, capped=True)
        self.assertFalse(report.complete)

    def test_a_parked_pass_is_not_complete(self):
        report = DeepSweepReport(listed=10, held=9, written_off=1, wanted=0, parked=True)
        self.assertFalse(report.complete)

    def test_a_pass_that_downloaded_everything_it_wanted_is_complete(self):
        report = DeepSweepReport(listed=10, held=7, written_off=0, wanted=3, downloaded=3)
        self.assertTrue(report.complete)

    def test_a_pass_that_left_a_track_behind_is_not_complete(self):
        report = DeepSweepReport(listed=10, held=7, written_off=0, wanted=3, downloaded=2)
        self.assertFalse(report.complete)

    def test_the_summary_names_every_number(self):
        report = DeepSweepReport(listed=10, held=7, written_off=1, wanted=2, downloaded=2)
        self.assertEqual('10 listed, 7 held, 1 written off, 2 wanted, 2 fetched', report.summary())


class FakeYDL:
    """Stands in for YoutubeDL, recording the options it was built with."""

    last: 'FakeYDL'

    def __init__(self, opts):
        self.opts = opts
        self.url = None
        FakeYDL.last = self

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        self.url = url
        return {
            'entries': [
                {'id': '1', 'url': 'https://example.test/1', 'title': 'one'},
                {'id': '2', 'url': 'https://example.test/2', 'title': 'two'},
                {'id': None, 'url': 'https://example.test/x', 'title': 'broken'},
            ]
        }


class ListFlatTest(unittest.TestCase):
    def test_it_returns_every_entry_that_has_an_id(self):
        tracks = list_flat('https://example.test/dj_a', {}, ydl_factory=FakeYDL)
        self.assertEqual(['1', '2'], [t.track_id for t in tracks])

    def test_it_keeps_the_permalink_and_the_title(self):
        first = list_flat('https://example.test/dj_a', {}, ydl_factory=FakeYDL)[0]
        self.assertEqual('https://example.test/1', first.url)
        self.assertEqual('one', first.title)

    def test_it_asks_for_a_flat_listing_and_no_download(self):
        list_flat('https://example.test/dj_a', {}, ydl_factory=FakeYDL)
        self.assertEqual('in_playlist', FakeYDL.last.opts['extract_flat'])
        self.assertTrue(FakeYDL.last.opts['skip_download'])
        self.assertNotIn('playlistend', FakeYDL.last.opts)

    def test_a_limit_stops_the_listing_early(self):
        list_flat('https://example.test/dj_a', {}, limit=1, ydl_factory=FakeYDL)
        self.assertEqual(1, FakeYDL.last.opts['playlistend'])

    def test_the_options_that_would_hide_entries_are_dropped(self):
        base = {
            'download_archive': '/tmp/a.txt',
            'break_on_existing': True,
            'match_filter': lambda info: None,
            'outtmpl': 'x',
            'format': 'mp3',
            'playlistend': 1,
            'cookiefile': '/tmp/c.txt',
        }
        list_flat('https://example.test/dj_a', base, ydl_factory=FakeYDL)
        for dropped in ('download_archive', 'break_on_existing', 'match_filter', 'outtmpl', 'format'):
            self.assertNotIn(dropped, FakeYDL.last.opts)
        self.assertNotIn('playlistend', FakeYDL.last.opts)

    def test_the_client_the_download_would_present_is_kept(self):
        base = {'cookiefile': '/tmp/c.txt', 'user_agent': 'Firefox/151.0'}
        list_flat('https://example.test/dj_a', base, ydl_factory=FakeYDL)
        self.assertEqual('/tmp/c.txt', FakeYDL.last.opts['cookiefile'])
        self.assertEqual('Firefox/151.0', FakeYDL.last.opts['user_agent'])

    def test_an_empty_listing_is_not_an_error(self):
        class Empty(FakeYDL):
            def extract_info(self, url, download=False):
                return {'entries': []}

        self.assertEqual([], list_flat('https://example.test/x', {}, ydl_factory=Empty))

    def test_no_listing_at_all_is_a_failure_not_an_empty_account(self):
        # What yt-dlp returns under `ignoreerrors` after a refused page. Counting
        # it as "0 listed" marked the account complete and skipped it for weeks.
        class Nothing(FakeYDL):
            def extract_info(self, url, download=False):
                return None

        with self.assertRaises(ListingFailed):
            list_flat('https://example.test/x', {}, ydl_factory=Nothing)

    def test_an_extraction_error_is_raised_as_a_listing_failure_that_keeps_the_status(self):
        class Refused(FakeYDL):
            def extract_info(self, url, download=False):
                raise RuntimeError('ERROR: Unable to download API page: HTTP Error 403: Forbidden')

        with self.assertRaises(ListingFailed) as raised:
            list_flat('https://example.test/x', {}, ydl_factory=Refused)
        self.assertIn('HTTP Error 403: Forbidden', str(raised.exception))
        self.assertEqual('https://example.test/x', raised.exception.url)

    def test_ignoreerrors_is_forced_off_whatever_the_caller_passes(self):
        list_flat('https://example.test/dj_a', {'ignoreerrors': True}, ydl_factory=FakeYDL)
        self.assertIs(False, FakeYDL.last.opts['ignoreerrors'])


class TextArchiveTest(unittest.TestCase):
    def test_it_reads_the_id_from_each_line(self):
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, 'dj_a.txt')
            with open(path, 'w', encoding='utf-8') as handle:
                handle.write('soundcloud 111\nyoutube abc_DEF\n\n')
            self.assertEqual({'111', 'abc_DEF'}, ids_in_text_archive(path))

    def test_a_missing_file_is_an_empty_set(self):
        self.assertEqual(set(), ids_in_text_archive('/nonexistent/dj_a.txt'))

    def test_no_path_is_an_empty_set(self):
        self.assertEqual(set(), ids_in_text_archive(None))
