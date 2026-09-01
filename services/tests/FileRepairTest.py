import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.other import repair
from services.other.repair import FileRepair


def make_repairer():
    """A FileRepair whose two database helpers are mocks, so nothing touches MariaDB."""
    with (
        patch.object(repair, 'BrokenSongHelper', return_value=MagicMock()),
        patch.object(repair, 'BrokenSongArtistLookupHelper', return_value=MagicMock()),
    ):
        return FileRepair()


class DeriveUrlTest(unittest.TestCase):
    def setUp(self):
        self.fix = make_repairer()

    def test_derive_soundcloud_url(self):
        self.fix.artist_lookup.get_normalized_name.return_value = 'artist'
        path = '/mnt/music/Soundcloud/Artist/Track Title.m4a'
        self.assertEqual(self.fix.derive_soundcloud_url(path), 'https://soundcloud.com/artist/track-title')

    def test_derive_soundcloud_url_percent_encodes_both_halves(self):
        self.fix.artist_lookup.get_normalized_name.return_value = 'düst & co'
        path = '/mnt/music/Soundcloud/Dust/Track & Title.m4a'
        url = self.fix.derive_soundcloud_url(path)
        self.assertEqual(url, 'https://soundcloud.com/d%C3%BCst%20%26%20co/track-%26-title')

    def test_derive_soundcloud_url_is_none_without_a_known_artist(self):
        self.fix.artist_lookup.get_normalized_name.return_value = None
        path = '/mnt/music/Soundcloud/Unknown/Track.m4a'
        self.assertIsNone(self.fix.derive_soundcloud_url(path))

    def test_derive_soundcloud_url_is_none_when_the_path_has_no_filename(self):
        self.fix.artist_lookup.get_normalized_name.return_value = 'artist'
        self.assertIsNone(self.fix.derive_soundcloud_url('/mnt/music/Soundcloud/artist'))

    def test_derive_youtube_url(self):
        path = '/mnt/music/Youtube/uploader/Video Title.m4a'
        self.assertEqual(self.fix.derive_youtube_url(path), 'https://www.youtube.com/watch?v=video-title')

    def test_derive_youtube_url_is_none_on_a_bad_path(self):
        self.assertIsNone(self.fix.derive_youtube_url(None))


class RepairTest(unittest.TestCase):
    def setUp(self):
        self.fix = make_repairer()
        self.fix.artist_lookup.get_normalized_name.return_value = 'artist'

    def test_a_successful_soundcloud_repair_reports_success_and_records_no_failure(self):
        with patch.object(self.fix, 'download_from_soundcloud', return_value=True) as download:
            self.assertTrue(self.fix.repair_soundcloud(1, '/mnt/music/Soundcloud/artist/Track.m4a'))
        download.assert_called_once()
        self.assertEqual(self.fix.failed_downloads, [])

    def test_a_failed_soundcloud_repair_is_remembered_and_the_artist_queued_for_lookup(self):
        with patch.object(self.fix, 'download_from_soundcloud', return_value=False):
            self.assertFalse(self.fix.repair_soundcloud(1, '/mnt/music/Soundcloud/Artist/Track.m4a'))
        self.fix.artist_lookup.insert_if_missing.assert_called_once_with('artist')
        self.assertEqual(len(self.fix.failed_downloads), 1)

    def test_soundcloud_repair_stops_when_no_url_can_be_derived(self):
        self.fix.artist_lookup.get_normalized_name.return_value = None
        with patch.object(self.fix, 'download_from_soundcloud') as download:
            self.assertFalse(self.fix.repair_soundcloud(1, '/mnt/music/Soundcloud/artist/Track.m4a'))
        download.assert_not_called()

    def test_a_successful_youtube_repair_reports_success(self):
        with patch.object(self.fix, 'download_from_youtube', return_value=True):
            self.assertTrue(self.fix.repair_youtube(2, '/mnt/music/Youtube/chan/Video.m4a'))
        self.assertEqual(self.fix.failed_downloads, [])

    def test_a_failed_youtube_repair_is_remembered(self):
        with patch.object(self.fix, 'download_from_youtube', return_value=False):
            self.assertFalse(self.fix.repair_youtube(2, '/mnt/music/Youtube/chan/Video.m4a'))
        self.assertEqual(len(self.fix.failed_downloads), 1)

    def test_youtube_repair_stops_when_no_url_can_be_derived(self):
        with (
            patch.object(self.fix, 'derive_youtube_url', return_value=None),
            patch.object(self.fix, 'download_from_youtube') as download,
        ):
            self.assertFalse(self.fix.repair_youtube(2, '/mnt/music/Youtube/chan/Video.m4a'))
        download.assert_not_called()


class RunTest(unittest.TestCase):
    def setUp(self):
        self.fix = make_repairer()

    def test_run_dispatches_each_row_to_the_matching_repairer(self):
        self.fix.broken_helper.get_all.return_value = [
            (1, '/mnt/music/Soundcloud/a/One.m4a', None),
            (2, '/mnt/music/Youtube/c/Two.m4a', None),
            (3, '/mnt/music/Labels/x/Three.m4a', None),
        ]
        with (
            patch.object(self.fix, 'import_accounts'),
            patch.object(self.fix, 'repair_soundcloud', return_value=True) as sc,
            patch.object(self.fix, 'repair_youtube', return_value=True) as yt,
            patch.object(self.fix, 'try_delete_file') as delete,
        ):
            self.fix.run()
        sc.assert_called_once_with(1, '/mnt/music/Soundcloud/a/One.m4a')
        yt.assert_called_once_with(2, '/mnt/music/Youtube/c/Two.m4a')
        self.assertEqual(delete.call_count, 2)
        self.assertEqual(self.fix.broken_helper.remove.call_count, 2)

    def test_run_keeps_the_row_and_the_file_when_the_repair_failed(self):
        self.fix.broken_helper.get_all.return_value = [(1, '/mnt/music/Soundcloud/a/One.m4a', None)]
        with (
            patch.object(self.fix, 'import_accounts'),
            patch.object(self.fix, 'repair_soundcloud', return_value=False),
            patch.object(self.fix, 'try_delete_file') as delete,
        ):
            self.fix.run()
        delete.assert_not_called()
        self.fix.broken_helper.remove.assert_not_called()

    def test_run_survives_a_helper_that_blows_up(self):
        self.fix.broken_helper.get_all.side_effect = RuntimeError('database gone')
        with patch.object(self.fix, 'import_accounts'):
            self.fix.run()  # must not raise

    def test_run_logs_the_permanently_failed_downloads(self):
        self.fix.broken_helper.get_all.return_value = []
        self.fix.failed_downloads = [(1, '/path.m4a', 'https://example.test/x')]
        with patch.object(self.fix, 'import_accounts'), self.assertLogs(level='WARNING') as logs:
            self.fix.run()
        self.assertTrue(any('https://example.test/x' in line for line in logs.output))


class ImportAccountsTest(unittest.TestCase):
    def setUp(self):
        self.fix = make_repairer()

    def test_a_missing_accounts_file_is_only_a_warning(self):
        with patch.object(repair.os.path, 'exists', return_value=False), self.assertLogs(level='WARNING'):
            self.fix.import_accounts()
        self.fix.artist_lookup.insert_if_missing.assert_not_called()

    def test_every_account_line_is_looked_up_and_stored(self):
        with tempfile.TemporaryDirectory() as tmp:
            accounts = Path(tmp) / 'accounts.txt'
            accounts.write_text('first\n\nsecond\n', encoding='utf-8')
            with (
                patch.object(repair.os.path, 'exists', return_value=True),
                patch.object(repair, 'open', lambda *a, **k: accounts.open('r', encoding='utf-8'), create=True),
                patch.object(self.fix, 'fetch_uploader_info', side_effect=['First Raw', None]),
            ):
                self.fix.import_accounts()
        self.fix.artist_lookup.insert_if_missing.assert_called_once_with('First Raw', 'first')


class DownloadTest(unittest.TestCase):
    def setUp(self):
        self.fix = make_repairer()

    def test_a_soundcloud_download_reports_success(self):
        with patch.object(repair, 'yt_dlp') as ydl_module:
            self.assertTrue(self.fix.download_from_soundcloud('https://x.test/y', '/tmp/out.m4a'))
        ydl_module.YoutubeDL.return_value.__enter__.return_value.download.assert_called_once_with(['https://x.test/y'])

    def test_a_soundcloud_download_error_is_swallowed(self):
        with patch.object(repair, 'yt_dlp') as ydl_module:
            ydl_module.YoutubeDL.side_effect = RuntimeError('boom')
            self.assertFalse(self.fix.download_from_soundcloud('https://x.test/y', '/tmp/out.m4a'))

    def test_a_youtube_download_reports_success(self):
        with patch.object(repair, 'yt_dlp') as ydl_module:
            self.assertTrue(self.fix.download_from_youtube('https://x.test/y', '/tmp/out.m4a'))
        ydl_module.YoutubeDL.return_value.__enter__.return_value.download.assert_called_once_with(['https://x.test/y'])

    def test_a_youtube_download_error_is_swallowed(self):
        with patch.object(repair, 'yt_dlp') as ydl_module:
            ydl_module.YoutubeDL.side_effect = RuntimeError('boom')
            self.assertFalse(self.fix.download_from_youtube('https://x.test/y', '/tmp/out.m4a'))

    def test_fetch_uploader_info_returns_the_uploader(self):
        with patch.object(repair, 'yt_dlp') as ydl_module:
            ydl_module.YoutubeDL.return_value.__enter__.return_value.extract_info.return_value = {'uploader': 'Someone'}
            self.assertEqual(self.fix.fetch_uploader_info('https://x.test/y'), 'Someone')

    def test_fetch_uploader_info_is_none_when_yt_dlp_fails(self):
        with patch.object(repair, 'yt_dlp') as ydl_module:
            ydl_module.YoutubeDL.side_effect = RuntimeError('boom')
            self.assertIsNone(self.fix.fetch_uploader_info('https://x.test/y'))


class DeleteFileTest(unittest.TestCase):
    def test_the_file_is_removed(self):
        fix = make_repairer()
        with tempfile.TemporaryDirectory() as tmp:
            target = Path(tmp) / 'gone.m4a'
            target.write_text('x')
            fix.try_delete_file(str(target))
            self.assertFalse(target.exists())

    def test_a_missing_file_is_only_a_warning(self):
        fix = make_repairer()
        with self.assertLogs(level='WARNING'):
            fix.try_delete_file('/does/not/exist.m4a')


if __name__ == '__main__':
    unittest.main()
