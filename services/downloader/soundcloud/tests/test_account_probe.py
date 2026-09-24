"""The one-request question: what is this account's newest track?"""

import unittest

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.deep_sweep import ListingFailed  # isort:skip
from services.downloader.soundcloud.account_probe import (  # isort:skip
    ProbeResult,
    newest_track,
)


class FakeYoutubeDL:
    """Stands in for YoutubeDL, recording the options it was handed."""

    last_opts: dict = {}
    last_url: str | None = None
    result: dict | None = None
    error: Exception | None = None

    def __init__(self, opts):
        FakeYoutubeDL.last_opts = opts

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def extract_info(self, url, download=False):
        FakeYoutubeDL.last_url = url
        if FakeYoutubeDL.error is not None:
            raise FakeYoutubeDL.error
        return FakeYoutubeDL.result


class NewestTrackTest(unittest.TestCase):
    def setUp(self):
        FakeYoutubeDL.last_opts = {}
        FakeYoutubeDL.last_url = None
        FakeYoutubeDL.error = None
        # Shaped like a real flat listing: newest first, and no timestamp.
        FakeYoutubeDL.result = {
            'entries': [
                {
                    'id': '2379459947',
                    'title': 'Dokho - Better Place',
                    'url': 'https://soundcloud.com/monstercat/dokho-better-place',
                },
                {'id': '2377500137', 'title': 'Oliverse - Risk It All', 'url': 'x'},
            ]
        }

    def probe(self, base_opts=None):
        return newest_track('monstercat', base_opts or {}, ydl_factory=FakeYoutubeDL)

    def test_it_returns_the_first_entry(self):
        self.assertEqual(
            self.probe(),
            ProbeResult('2379459947', 'Dokho - Better Place', 'https://soundcloud.com/monstercat/dokho-better-place'),
        )

    def test_it_asks_for_the_account_tracks_page(self):
        self.probe()
        self.assertEqual(FakeYoutubeDL.last_url, 'https://soundcloud.com/monstercat/tracks')

    def test_it_reads_one_flat_entry_and_no_more(self):
        self.probe()
        opts = FakeYoutubeDL.last_opts
        self.assertEqual(opts['extract_flat'], 'in_playlist')
        self.assertIs(opts['lazy_playlist'], True)
        self.assertEqual(opts['playlistend'], 1)

    def test_it_drops_the_options_that_would_hide_the_newest_track(self):
        # break_on_existing raises on exactly the case the probe exists to
        # detect, and download_archive would make yt-dlp skip the entry.
        self.probe(
            {'download_archive': '/tmp/archive.txt', 'break_on_existing': True, 'match_filter': lambda info: None}
        )
        opts = FakeYoutubeDL.last_opts
        self.assertNotIn('download_archive', opts)
        self.assertNotIn('break_on_existing', opts)
        self.assertNotIn('match_filter', opts)

    def test_it_keeps_the_headers_and_cookies_it_was_given(self):
        self.probe({'http_headers': {'User-Agent': 'muma/1.0'}, 'cookies': 'soundcloud.com_cookies.txt'})
        opts = FakeYoutubeDL.last_opts
        self.assertEqual(opts['http_headers'], {'User-Agent': 'muma/1.0'})
        self.assertEqual(opts['cookies'], 'soundcloud.com_cookies.txt')

    def test_it_does_not_mutate_the_options_it_was_handed(self):
        base = {'break_on_existing': True, 'http_headers': {}}
        self.probe(base)
        self.assertIn('break_on_existing', base)

    def test_an_account_with_no_tracks_gives_nothing(self):
        FakeYoutubeDL.result = {'entries': []}
        self.assertIsNone(self.probe())

    def test_an_extraction_that_returned_nothing_is_a_failure_not_an_empty_account(self):
        # What yt-dlp hands back under `ignoreerrors` after a refused page. Reading
        # it as "no tracks" is how a 403 used to pass for a finished account.
        FakeYoutubeDL.result = None
        with self.assertRaises(ListingFailed):
            self.probe()

    def test_ignoreerrors_is_forced_off_for_the_listing(self):
        self.probe({'ignoreerrors': True})
        self.assertIs(FakeYoutubeDL.last_opts['ignoreerrors'], False)

    def test_an_entry_without_an_id_gives_nothing(self):
        FakeYoutubeDL.result = {'entries': [{'title': 'no id here'}]}
        self.assertIsNone(self.probe())

    def test_a_numeric_id_is_returned_as_a_string(self):
        FakeYoutubeDL.result = {'entries': [{'id': 2379459947, 'title': 't', 'url': 'u'}]}
        self.assertEqual(self.probe().track_id, '2379459947')

    def test_a_failure_is_raised_for_the_caller_to_classify(self):
        # Only the caller knows whether a 403 should park the source or fall
        # through to a full run.
        FakeYoutubeDL.error = RuntimeError('HTTP Error 403: Forbidden')
        with self.assertRaises(ListingFailed) as raised:
            self.probe()
        # yt-dlp's own text survives, so the policy can still read the status.
        self.assertIn('HTTP Error 403: Forbidden', str(raised.exception))


if __name__ == '__main__':
    unittest.main()
