"""The upload date reaches FFmpegMetadata delimited, in both downloaders (bug report 088).

EmbedThumbnail remuxes an mp3 as ID3v2.3, and ffmpeg keeps month and day through that
only for a `YYYY-MM-DD` date; the undelimited `upload_date` was cut to the year. The
end-to-end proof against real yt-dlp, ffmpeg and mutagen is
tests/unit/test_download_date_real_ffmpeg.py; this pins the post-processor and that
each downloader registers it ahead of the metadata step.
"""

import unittest
from unittest import mock
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.mock_base('yt_dlp', 'config_store', 'Cache')


from services.downloader.metadata_date import IsoUploadDatePP  # isort:skip
from services.downloader.rate_state import InMemoryRateStateStore, RateState  # isort:skip
from services.downloader.timing import load_timing  # isort:skip
from services.downloader.youtube.youtube import YoutubeDownloader  # isort:skip


class IsoUploadDatePPTest(unittest.TestCase):
    def test_a_full_upload_date_becomes_the_delimited_metadata_date(self):
        _, info = IsoUploadDatePP().run({'upload_date': '20260831'})

        self.assertEqual(info['meta_date'], '2026-08-31')

    def test_a_date_somebody_already_chose_is_kept(self):
        _, info = IsoUploadDatePP().run({'upload_date': '20260831', 'meta_date': '2026-09-01'})

        self.assertEqual(info['meta_date'], '2026-09-01')

    def test_without_a_full_upload_date_nothing_is_overridden(self):
        for info in ({}, {'upload_date': None}, {'upload_date': '2026'}):
            with self.subTest(info=info):
                _, out = IsoUploadDatePP().run(dict(info))
                self.assertNotIn('meta_date', out)


class SoundcloudWiringTest(unittest.TestCase):
    """The date post-processor is registered for the pre_process stage, before the metadata one."""

    @patch('services.downloader.soundcloud.soundcloud.YoutubeDL')
    def test_the_date_post_processor_runs_before_ffmpeg_metadata(self, mock_ytdlp):
        from services.downloader.soundcloud.soundcloud import SoundcloudDownloader

        downloader = SoundcloudDownloader.__new__(SoundcloudDownloader)
        downloader.policy = mock.MagicMock()
        downloader.policy.timing.retry_attempts = 1
        downloader.unavailable = mock.MagicMock()
        downloader._settle = mock.MagicMock()

        downloader._download_url('https://soundcloud.com/a/tracks', {}, 'a', None)

        calls = mock_ytdlp.return_value.__enter__.return_value.add_post_processor.call_args_list
        first = calls[0]
        self.assertIsInstance(first.args[0], IsoUploadDatePP)
        self.assertEqual(first.kwargs.get('when'), 'pre_process')


class YoutubeWiringTest(unittest.TestCase):
    def setUp(self):
        mock.patch('os.makedirs').start()
        self.addCleanup(mock.patch.stopall)
        timing = load_timing('youtube', overrides={})
        self.downloader = YoutubeDownloader(
            timing=timing,
            rate_state=RateState('youtube', timing, store=InMemoryRateStateStore()),
        )

    @patch('services.downloader.youtube.youtube.YoutubeDL')
    def test_the_date_post_processor_is_registered_for_pre_process(self, mock_ytdlp):
        self.downloader._create_ydl({})

        registered = [
            call
            for call in mock_ytdlp.return_value.add_post_processor.call_args_list
            if isinstance(call.args[0], IsoUploadDatePP)
        ]
        self.assertEqual(len(registered), 1)
        self.assertEqual(registered[0].kwargs.get('when'), 'pre_process')


if __name__ == '__main__':
    unittest.main()
