"""Both downloaders must ask yt-dlp to write the thumbnail, not only to embed it.

`EmbedThumbnail` embeds a thumbnail *file*: it looks for `info['thumbnails'][i]['filepath']`
and, finding none, prints "There are no thumbnails on disk" and hands the info back
untouched. The CLI's `--embed-thumbnail` implies `--write-thumbnail`; adding the
post-processor through the Python API does not. Nothing failed when that was missing -- the
downloads landed, the post-processor ran, and the files simply had no artwork. Production
had it in 387 of 149.626 SoundCloud tracks before this was fixed, and the web UI drew the
placeholder for the rest.

So the option is pinned per downloader rather than trusted: this is exactly the kind of
setting a rewrite of the options dict drops without a single test going red.
"""

import unittest
from unittest import mock
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('yt_dlp', 'config_store')


from services.downloader.rate_state import InMemoryRateStateStore, RateState  # isort:skip
from services.downloader.soundcloud import soundcloud as soundcloud_module  # isort:skip
from services.downloader.soundcloud.soundcloud import SoundcloudDownloader  # isort:skip
from services.downloader.timing import load_timing  # isort:skip
from services.downloader.youtube.youtube import YoutubeDownloader  # isort:skip

SOUNDCLOUD_CONFIG = {
    'soundcloud_folder': '/music/soundcloud',
    'soundcloud_archive': '/data/archive',
    'soundcloud_cookies': 'soundcloud.com_cookies.txt',
    'ffmpeg_location': '/usr/bin',
    'soundcloud_user_agent': '',
}


class SoundcloudArtworkTest(unittest.TestCase):
    def options(self):
        downloader = SoundcloudDownloader.__new__(SoundcloudDownloader)
        downloader._config = MagicMock()
        downloader._config.get_many.return_value = SOUNDCLOUD_CONFIG
        downloader.dry_run = False
        downloader.default_break_on_existing = False
        downloader.redownload_mode = False
        downloader._profile_snapshot = None
        downloader.policy = MagicMock()
        downloader.policy.timing.to_ydl_opts.return_value = {}
        with (
            patch.object(soundcloud_module.os, 'makedirs'),
            patch.object(soundcloud_module.os.path, 'isfile', return_value=True),
        ):
            downloader._apply_config()
        return downloader.downloader_config['ydl_opts']

    def test_the_thumbnail_is_written_so_the_post_processor_has_one_to_embed(self):
        self.assertIs(True, self.options().get('writethumbnail'))


class YoutubeArtworkTest(unittest.TestCase):
    def setUp(self):
        mock.patch('os.makedirs').start()
        self.addCleanup(mock.patch.stopall)
        timing = load_timing('youtube', overrides={})
        self.downloader = YoutubeDownloader(
            timing=timing,
            rate_state=RateState('youtube', timing, store=InMemoryRateStateStore()),
        )

    def test_the_thumbnail_is_written_so_the_post_processor_has_one_to_embed(self):
        options = self.downloader._base_ydl_opts

        self.assertIs(True, options.get('writethumbnail'))
        self.assertIn({'key': 'EmbedThumbnail'}, options['postprocessors'])

    def test_a_video_channel_inherits_it_too(self):
        # `_video_ydl_opts` is empty unless a video folder is configured, which the test
        # config has none of, so the options are rebuilt here with one.
        self.downloader.downloader_config['video_folder'] = '/music/youtube-video'
        options = self.downloader._build_video_base_opts()

        self.assertIs(True, options.get('writethumbnail'))


class YoutubeAudioFormatTest(YoutubeArtworkTest):
    """An audio channel asks for the audio stream only (bug report 130).

    Without a format, yt-dlp's default fetched and merged the whole video before
    FFmpegExtractAudio threw it away again, and warned on every download that the
    webm merge had to become an mkv for the thumbnail.
    """

    def test_an_audio_channel_downloads_only_the_audio_stream(self):
        self.assertEqual('bestaudio/best', self.downloader._base_ydl_opts.get('format'))

    def test_a_video_channel_still_merges_video_and_audio(self):
        self.downloader.downloader_config['video_folder'] = '/music/youtube-video'
        options = self.downloader._build_video_base_opts()

        self.assertEqual('bestvideo*+bestaudio/best', options['format'])
        self.assertEqual('mkv', options['merge_output_format'])


if __name__ == '__main__':
    unittest.main()
