"""The video branch of the YouTube downloader.

`downloads_youtube_accounts.download_type` had been sitting in the database
unused, so a channel marked as video was swept as audio instead — twice, for the
seven channels that carry both rows. These tests pin down the split.
"""

import unittest
from unittest.mock import patch

from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()
from services.downloader.rate_state import RateLimited
from services.downloader.timing import load_timing
from services.downloader.youtube.youtube import VIDEO_FORMAT, YoutubeDownloader
from services.downloader.youtube.YoutubeAccount import YoutubeAccount


class YoutubeVideoDownloaderTest(unittest.TestCase):
    def setUp(self):
        self.patchers = []
        config_patcher = patch('services.downloader.youtube.youtube.ConfigStore')
        self.mock_config = config_patcher.start()
        self.patchers.append(config_patcher)
        self.mock_config.return_value.get_many.return_value = {
            'youtube_folder': '/tmp/youtube',
            'youtube_video_folder': '/tmp/youtube_video',
            'youtube_archive': '/tmp/archive',
        }
        reset_database_helpers()
        for target in ('os.makedirs', 'os.path.exists', 'os.path.isdir'):
            patcher = patch(target)
            mock = patcher.start()
            self.patchers.append(patcher)
            if target != 'os.makedirs':
                mock.return_value = True

    def tearDown(self):
        for patcher in self.patchers:
            patcher.stop()
        patch.stopall()

    def _downloader(self):
        # These tests drive the ordinary run. Without turning the cadence off
        # every channel would be deep-due -- none has ever been deep-swept --
        # and take the full-listing path instead.
        downloader = YoutubeDownloader(
            break_on_existing=False, timing=load_timing('youtube', overrides={'deep_sweep_days': 0})
        )
        downloader.downloader_config['enabled'] = True
        return downloader

    def test_video_options_keep_the_video_and_ask_for_the_best_streams(self):
        downloader = self._downloader()
        account = YoutubeAccount(name='@qdance', download_type='video', min_duration=1200)

        opts = downloader._prepare_ydl_opts(account, None, False)

        self.assertEqual(opts['format'], VIDEO_FORMAT)
        self.assertEqual(opts['merge_output_format'], 'mkv')
        keys = [pp['key'] for pp in opts['postprocessors']]
        self.assertNotIn('FFmpegExtractAudio', keys)

    def test_video_downloads_land_outside_the_music_library(self):
        downloader = self._downloader()
        account = YoutubeAccount(name='@qdance', download_type='video')

        opts = downloader._prepare_ydl_opts(account, None, False)

        self.assertTrue(opts['outtmpl'].startswith('/tmp/youtube_video/'))
        self.assertIn('/tmp/archive/video/', opts['download_archive'])

    def test_audio_options_are_unchanged(self):
        downloader = self._downloader()
        account = YoutubeAccount(name='Noisia')

        opts = downloader._prepare_ydl_opts(account, None, False)

        self.assertNotIn('format', opts)
        self.assertTrue(opts['outtmpl'].startswith('/tmp/youtube/'))
        keys = [pp['key'] for pp in opts['postprocessors']]
        self.assertIn('FFmpegExtractAudio', keys)

    def test_the_duration_floor_comes_from_the_account_row(self):
        downloader = self._downloader()
        account = YoutubeAccount(name='@qdance', download_type='video', min_duration=1200)

        match_filter = downloader._filter_for(account)

        with patch('services.downloader.youtube.youtube.YoutubeArchive') as archive:
            archive.exists.return_value = False
            self.assertIsNotNone(match_filter({'duration': 300, 'title': 'Teaser', 'id': 'x'}))
            self.assertIsNone(match_filter({'duration': 5400, 'title': 'Full set', 'id': 'y'}))

    def test_the_archive_is_checked_per_download_type(self):
        downloader = self._downloader()
        account = YoutubeAccount(name='@qdance', download_type='video', min_duration=60)

        match_filter = downloader._filter_for(account)

        with patch('services.downloader.youtube.youtube.YoutubeArchive') as archive:
            archive.exists.return_value = False
            match_filter({'duration': 5400, 'title': 'Set', 'id': 'vid', 'uploader_id': '@qdance'})
            archive.exists.assert_called_once_with('@qdance', 'vid', 'video')

    def test_video_is_skipped_without_ffmpeg(self):
        """Without ffmpeg yt-dlp silently drops to the 360p progressive stream."""
        downloader = self._downloader()

        with patch('os.path.exists', return_value=False), patch('shutil.which', return_value=None):
            self.assertFalse(downloader._video_ready())

    def test_video_is_skipped_without_a_configured_folder(self):
        self.mock_config.return_value.get_many.return_value = {
            'youtube_folder': '/tmp/youtube',
            'youtube_archive': '/tmp/archive',
        }
        downloader = self._downloader()

        self.assertFalse(downloader._video_ready())

    def test_audio_runs_before_video_and_both_run(self):
        downloader = self._downloader()
        downloader.get_accounts_from_db = lambda: [
            YoutubeAccount(name='@qdance', download_type='video', min_duration=1200),
            YoutubeAccount(name='Noisia'),
        ]
        seen = []
        downloader.download_account = lambda account, opts=None: seen.append(account.download_type)
        downloader.policy.due = lambda accounts: list(accounts)

        downloader.run()

        self.assertEqual(seen, ['audio', 'video'])

    def test_a_rate_limit_during_audio_stops_the_video_pass(self):
        downloader = self._downloader()
        downloader.get_accounts_from_db = lambda: [
            YoutubeAccount(name='@qdance', download_type='video', min_duration=1200),
            YoutubeAccount(name='Noisia'),
        ]
        seen = []

        def refuse(account, opts=None):
            seen.append(account.download_type)
            raise RateLimited('youtube', 3600, '429')

        downloader.download_account = refuse
        downloader.policy.due = lambda accounts: list(accounts)

        downloader.run()

        self.assertEqual(seen, ['audio'])

    def test_the_schedule_keeps_audio_and_video_of_one_channel_apart(self):
        downloader = self._downloader()
        downloader.get_accounts_from_db = lambda: [
            YoutubeAccount(name='@qdance', download_type='video', min_duration=1200),
            YoutubeAccount(name='@qdance'),
        ]
        downloader.download_account = lambda account, opts=None: None
        downloader.policy.due = lambda accounts: list(accounts)
        marked = []
        downloader.policy.mark_checked = marked.append

        downloader.run()

        self.assertEqual(sorted(marked), ['@qdance', '@qdance#video'])

    def test_inactive_accounts_are_skipped(self):
        downloader = self._downloader()
        downloader.get_accounts_from_db = lambda: [
            YoutubeAccount(name='Noisia'),
            YoutubeAccount(name='Retired', active=False),
        ]

        names = [account.name for account in downloader._get_accounts('')]

        self.assertEqual(names, ['Noisia'])


class YoutubeAccountRowTest(unittest.TestCase):
    def test_a_short_row_falls_back_to_the_old_behaviour(self):
        account = YoutubeAccount.from_row(('Noisia',))

        self.assertEqual(account.download_type, 'audio')
        self.assertEqual(account.min_duration, 60)
        self.assertTrue(account.active)

    def test_nulls_from_a_pre_migration_database_are_tolerated(self):
        account = YoutubeAccount.from_row(('Noisia', None, None, None))

        self.assertEqual(account.download_type, 'audio')
        self.assertEqual(account.min_duration, 60)
        self.assertTrue(account.active)

    def test_a_video_row_gets_its_own_schedule_key(self):
        audio = YoutubeAccount.from_row(('@qdance', 'audio', 60, 1))
        video = YoutubeAccount.from_row(('@qdance', 'video', 1200, 1))

        self.assertEqual(audio.schedule_key, '@qdance')
        self.assertEqual(video.schedule_key, '@qdance#video')
        self.assertNotEqual(audio.schedule_key, video.schedule_key)


if __name__ == '__main__':
    unittest.main()
