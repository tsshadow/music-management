"""A missing image provider is reported once per process, not once per fetcher.

`trigger_fetch_by_id` builds a new ArtistImageFetcher for every single-artist fetch
from the manager, and each construction used to log "Spotify credentials not found",
"Last.fm API key not found" and "no configured image provider" again -- each one a push
on the alerts topic whenever the five-minute brake had lapsed. Bug report 065.
"""

import logging
import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.music_manager.artist_image_fetcher import fetcher as fetcher_module
from services.music_manager.artist_image_fetcher.fetcher import ArtistImageFetcher
from services.music_manager.artist_image_fetcher.providers import base, lastfm, spotify

SPOTIFY_MISSING = 'Spotify API credentials'
LASTFM_MISSING = 'Last.fm API key'
NO_PROVIDER = 'no configured image provider'


class SetupWarningsTest(unittest.TestCase):
    """Two fetchers without credentials: one WARNING/ERROR per complaint, then DEBUG."""

    def setUp(self):
        base.forget_logged_once()
        self.addCleanup(base.forget_logged_once)
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        for patcher in (
            patch.dict(os.environ, {'ARTIST_IMAGE_STORAGE_PATH': tmp.name}),
            patch.object(spotify, 'credential', return_value=None),
            patch.object(lastfm, 'credential', return_value=None),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def build(self):
        """Construct one fetcher the way the router does, and return its log records."""
        loggers = [fetcher_module.__name__, spotify.__name__, lastfm.__name__]
        with self.assertLogs(level=logging.DEBUG) as logs:
            ArtistImageFetcher(db_conn=MagicMock())
        return [r for r in logs.records if r.name in loggers]

    @staticmethod
    def levels(records, fragment):
        """The level names of the records whose message contains `fragment`."""
        return [r.levelname for r in records if fragment in r.getMessage()]

    def test_two_constructions_log_each_complaint_once_at_full_level(self):
        first, second = self.build(), self.build()
        self.assertEqual(self.levels(first, SPOTIFY_MISSING), ['WARNING'])
        self.assertEqual(self.levels(first, LASTFM_MISSING), ['WARNING'])
        self.assertEqual(self.levels(first, NO_PROVIDER), ['ERROR'])
        self.assertEqual(self.levels(second, SPOTIFY_MISSING), ['DEBUG'])
        self.assertEqual(self.levels(second, LASTFM_MISSING), ['DEBUG'])
        self.assertEqual(self.levels(second, NO_PROVIDER), ['DEBUG'])

    def test_credentials_that_come_back_rearm_the_warning(self):
        self.build()
        spotify.SpotifyArtistImageProvider(client_id='id', client_secret='secret')
        again = self.build()
        self.assertEqual(self.levels(again, SPOTIFY_MISSING), ['WARNING'])
        self.assertEqual(self.levels(again, LASTFM_MISSING), ['DEBUG'])


class LogOnceTest(unittest.TestCase):
    """The helper itself: first call at its level, later calls at DEBUG, per key."""

    def setUp(self):
        base.forget_logged_once()
        self.addCleanup(base.forget_logged_once)
        self.logger = logging.getLogger('test.log_once')

    def test_keys_are_independent(self):
        with self.assertLogs(self.logger, level=logging.DEBUG) as logs:
            base.log_once(self.logger, 'a', logging.WARNING, 'a missing')
            base.log_once(self.logger, 'b', logging.WARNING, 'b missing')
            base.log_once(self.logger, 'a', logging.WARNING, 'a missing')
        self.assertEqual([r.levelname for r in logs.records], ['WARNING', 'WARNING', 'DEBUG'])


if __name__ == '__main__':
    unittest.main()
