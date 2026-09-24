"""A redownload replaces the library file in one rename, and only once the new one is complete.

yt-dlp answered "has already been downloaded" for an existing file, which made every
YouTube redownload a no-op; told to overwrite, it deletes the old file before fetching
the new one. services/downloader/redownload.py stages the download beside the target
and moves it over the old file after yt-dlp's post-processors and before the tagger's.
The real yt-dlp is exercised in tests/unit/test_downloader_real_ytdlp.py.
"""

import os
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader import redownload  # isort:skip
from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore  # isort:skip
from services.downloader.rate_state import InMemoryRateStateStore, RateState  # isort:skip
from services.downloader.timing import load_timing  # isort:skip
from services.downloader.write_offs import InMemoryWriteOffStore, WriteOffs  # isort:skip
from services.downloader.youtube import youtube as youtube_module  # isort:skip


class FolderTestCase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.folder = os.path.join(self.tmp.name, 'Youtube', 'Channel')
        os.makedirs(self.folder)
        self.target = os.path.join(self.folder, 'Track.m4a')
        with open(self.target, 'w') as handle:
            handle.write('old')

    def read(self, path):
        with open(path) as handle:
            return handle.read()


class RedownloadOptsTest(unittest.TestCase):
    def test_yt_dlp_is_told_to_overwrite_and_the_old_spelling_is_dropped(self):
        opts = redownload.redownload_opts({'nooverwrites': True, 'quiet': True})
        self.assertEqual(opts, {'overwrites': True, 'quiet': True})

    def test_the_callers_options_are_not_changed(self):
        original = {'nooverwrites': True}
        redownload.redownload_opts(original)
        self.assertEqual(original, {'nooverwrites': True})


class StagedOptsTest(FolderTestCase):
    def test_the_download_is_staged_in_a_hidden_folder_beside_the_target(self):
        with redownload.staged_opts({'outtmpl': '/elsewhere/%(title)s.%(ext)s'}, self.target) as opts:
            staging = os.path.dirname(opts['outtmpl'])
            self.assertEqual(os.path.dirname(staging), self.folder, 'same filesystem, so the rename is atomic')
            self.assertTrue(os.path.basename(staging).startswith('.'))
            self.assertTrue(os.path.isdir(staging))
            self.assertIs(opts['overwrites'], True)
        self.assertFalse(os.path.exists(staging))

    def test_a_failed_download_leaves_the_old_file_and_no_staging_folder(self):
        with self.assertRaises(RuntimeError), redownload.staged_opts({}, self.target) as opts:
            with open(os.path.join(os.path.dirname(opts['outtmpl']), 'abc.m4a.part'), 'w') as handle:
                handle.write('half')
            raise RuntimeError('403')
        self.assertEqual(self.read(self.target), 'old')
        self.assertEqual(os.listdir(self.folder), ['Track.m4a'])


class ReplaceTargetTest(FolderTestCase):
    def stage(self, name, content='new'):
        path = os.path.join(self.tmp.name, name)
        with open(path, 'w') as handle:
            handle.write(content)
        return path

    def test_the_same_extension_replaces_the_file_in_place(self):
        final = redownload.replace_target(self.stage('abc.m4a'), self.target)
        self.assertEqual(final, self.target)
        self.assertEqual(self.read(self.target), 'new')

    def test_the_extension_is_compared_without_case(self):
        self.assertEqual(redownload.replace_target(self.stage('abc.M4A'), self.target), self.target)

    def test_another_format_lands_beside_the_old_name_and_the_old_file_goes(self):
        final = redownload.replace_target(self.stage('abc.mp3'), self.target)
        self.assertEqual(final, os.path.join(self.folder, 'Track.mp3'))
        self.assertEqual(os.listdir(self.folder), ['Track.mp3'])


class ReplaceExistingPPTest(FolderTestCase):
    def test_the_info_dict_points_at_the_library_path_afterwards(self):
        staged = os.path.join(self.tmp.name, 'abc.m4a')
        with open(staged, 'w') as handle:
            handle.write('new')
        info = {'filepath': staged, 'requested_downloads': [{'filepath': staged}]}
        _, info = redownload.ReplaceExistingPP(self.target).run(info)
        self.assertEqual(info['filepath'], self.target)
        self.assertEqual(info['_filename'], self.target)
        self.assertEqual(info['requested_downloads'][0]['filepath'], self.target)
        self.assertTrue(info[redownload.REPLACED_KEY])
        self.assertEqual(self.read(self.target), 'new')

    def test_yt_dlp_does_not_move_the_file_back_into_the_staging_folder(self):
        # MoveFilesAfterDownloadPP moves `filepath` into `__finaldir`, the template's folder --
        # the staging folder, deleted right after. Found by the real-yt-dlp test.
        staging = tempfile.mkdtemp(dir=self.tmp.name)
        staged = os.path.join(staging, 'abc.m4a')
        thumbnail = os.path.join(staging, 'abc.webp')
        for path in (staged, thumbnail):
            with open(path, 'w') as handle:
                handle.write('new')
        info = {'filepath': staged, '__finaldir': staging, '__files_to_move': {thumbnail: None, '/x/sub.vtt': None}}
        _, info = redownload.ReplaceExistingPP(self.target).run(info)
        self.assertEqual(info['__finaldir'], self.folder)
        self.assertEqual(info['__files_to_move'], {'/x/sub.vtt': None}, 'staging leftovers stay to be deleted')

    def test_nothing_downloaded_leaves_the_old_file(self):
        info = {'filepath': os.path.join(self.tmp.name, 'missing.m4a')}
        with self.assertLogs(level='WARNING'):
            _, info = redownload.ReplaceExistingPP(self.target).run(info)
        self.assertNotIn(redownload.REPLACED_KEY, info)
        self.assertEqual(self.read(self.target), 'old')


class YoutubeRedownloadTest(FolderTestCase):
    def setUp(self):
        super().setUp()
        config = patch.object(youtube_module, 'ConfigStore')
        self.addCleanup(config.stop)
        config.start().return_value.get_many.return_value = {
            'youtube_folder': os.path.join(self.tmp.name, 'Youtube'),
            'youtube_archive': os.path.join(self.tmp.name, 'archive'),
            'yt_cookies': os.path.join(self.tmp.name, 'cookies.txt'),
        }
        with open(os.path.join(self.tmp.name, 'cookies.txt'), 'w') as handle:
            handle.write('# Netscape HTTP Cookie File\n')
        timing = load_timing('youtube', overrides={})
        self.downloader = youtube_module.YoutubeDownloader(
            timing=timing,
            rate_state=RateState('youtube', timing, store=InMemoryRateStateStore()),
            schedule=AccountSchedule('youtube', store=InMemoryCheckStore()),
            write_offs=WriteOffs('youtube', store=InMemoryWriteOffStore(), retry_days=30),
            notifier=MagicMock(),
        )

    def test_the_configured_downloads_never_overwrite(self):
        opts = self.downloader._build_ydl_opts('/archive.txt')
        self.assertIs(opts['nooverwrites'], True)
        self.assertNotIn('overwrites', opts)

    def test_a_redownload_overwrites(self):
        # nooverwrites made yt-dlp report "already downloaded" and change nothing.
        opts = self.downloader._build_ydl_opts('/archive.txt', redownload=True)
        self.assertIs(opts['overwrites'], True)
        self.assertNotIn('nooverwrites', opts)

    def test_a_replacement_is_staged_and_put_in_place_before_the_tagger_runs(self):
        with patch.object(youtube_module, 'YoutubeDL') as ydl_class:
            self.downloader.download_link(
                'https://youtu.be/x', breakOnExisting=False, redownload=True, replace=self.target
            )
        opts = ydl_class.call_args.args[0]
        self.assertTrue(opts['outtmpl'].startswith(os.path.join(self.folder, redownload.STAGING_PREFIX)))
        self.assertIs(opts['overwrites'], True)
        added = [type(call.args[0]).__name__ for call in ydl_class.return_value.add_post_processor.call_args_list]
        self.assertLess(added.index('ReplaceExistingPP'), added.index('YoutubeSongProcessor'))
        self.assertEqual(os.listdir(self.folder), ['Track.m4a'], 'the staging folder is gone afterwards')
        self.assertIsNone(self.downloader._replace_target)

    def test_a_plain_download_is_not_staged(self):
        with patch.object(youtube_module, 'YoutubeDL') as ydl_class:
            self.downloader.download_link('https://youtu.be/x')
        added = [type(call.args[0]).__name__ for call in ydl_class.return_value.add_post_processor.call_args_list]
        self.assertNotIn('ReplaceExistingPP', added)


if __name__ == '__main__':
    unittest.main()
