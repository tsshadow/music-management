import subprocess
import unittest
from unittest.mock import MagicMock, patch

from services.other import converter
from services.other.converter import Converter


class ConverterTestCase(unittest.TestCase):
    def setUp(self):
        patcher = patch.object(converter, 's', MagicMock(music_folder_path='/music'))
        patcher.start()
        self.addCleanup(patcher.stop)
        self.converter = Converter()


class ScanFolderTest(ConverterTestCase):
    def scan(self, listing, folders=()):
        with (
            patch.object(converter.os, 'listdir', return_value=listing),
            patch.object(converter.os.path, 'isfile', side_effect=lambda p: p.rsplit('/', 1)[-1] not in folders),
            patch.object(converter.os.path, 'isdir', side_effect=lambda p: p.rsplit('/', 1)[-1] in folders),
            patch.object(self.converter, 'handle_file') as handle_file,
            patch.object(self.converter, 'scan_folder', wraps=self.converter.scan_folder) as scan_folder,
        ):
            self.converter.scan_folder('/music')
        return handle_file, scan_folder

    def test_every_file_in_the_folder_is_offered_to_the_handler(self):
        handle_file, _ = self.scan(['a.aac', 'b.m4a'])
        self.assertEqual(handle_file.call_count, 2)

    def test_subfolders_are_walked_recursively(self):
        with (
            patch.object(converter.os, 'listdir', side_effect=[['sub'], ['a.aac']]),
            patch.object(converter.os.path, 'isfile', side_effect=lambda p: p.endswith('.aac')),
            patch.object(converter.os.path, 'isdir', side_effect=lambda p: p.endswith('sub')),
            patch.object(self.converter, 'handle_file') as handle_file,
        ):
            self.converter.scan_folder('/music')
        handle_file.assert_called_once_with('/music/sub', 'a.aac')

    def test_synology_metadata_folders_are_not_walked(self):
        with (
            patch.object(converter.os, 'listdir', return_value=['@eaDir']) as listdir,
            patch.object(converter.os.path, 'isfile', return_value=False),
            patch.object(converter.os.path, 'isdir', return_value=True),
        ):
            self.converter.scan_folder('/music')
        self.assertEqual(listdir.call_count, 1)

    def test_run_starts_the_scan_at_the_configured_music_folder(self):
        with patch.object(self.converter, 'scan_folder') as scan_folder:
            self.converter.run()
        scan_folder.assert_called_once_with('/music')


class HandleFileTest(ConverterTestCase):
    def test_an_aac_file_is_converted(self):
        with (
            patch.object(self.converter, 'convert_file') as convert,
            patch.object(self.converter, 'cleanup_temp_file') as cleanup,
        ):
            self.converter.handle_file('/music', 'song.AAC')
        convert.assert_called_once_with('/music/song.AAC')
        cleanup.assert_not_called()

    def test_a_leftover_temp_file_is_offered_for_cleanup(self):
        with (
            patch.object(self.converter, 'convert_file') as convert,
            patch.object(self.converter, 'cleanup_temp_file') as cleanup,
        ):
            self.converter.handle_file('/music', 'song.temp.m4a')
        cleanup.assert_called_once_with('/music/song.temp.m4a')
        convert.assert_not_called()

    def test_any_other_file_is_ignored(self):
        with (
            patch.object(self.converter, 'convert_file') as convert,
            patch.object(self.converter, 'cleanup_temp_file') as cleanup,
        ):
            self.converter.handle_file('/music', 'song.flac')
        convert.assert_not_called()
        cleanup.assert_not_called()


class ConvertFileTest(ConverterTestCase):
    def test_an_aac_whose_m4a_already_exists_is_simply_deleted(self):
        with (
            patch.object(converter.os.path, 'exists', return_value=True),
            patch.object(converter.os, 'remove') as remove,
            patch.object(converter.subprocess, 'run') as run,
        ):
            self.converter.convert_file('/music/song.aac')
        remove.assert_called_once_with('/music/song.aac')
        run.assert_not_called()

    def test_a_successful_conversion_removes_the_original(self):
        with (
            patch.object(converter.os.path, 'exists', side_effect=[False, True]),
            patch.object(converter.os, 'remove') as remove,
            patch.object(converter.subprocess, 'run') as run,
        ):
            self.converter.convert_file('/music/song.aac')
        self.assertEqual(run.call_args.args[0][:2], ['/usr/bin/ffmpeg', '-y'])
        self.assertIn('/music/song.m4a', run.call_args.args[0])
        remove.assert_called_once_with('/music/song.aac')

    def test_a_conversion_that_produced_no_output_keeps_the_original(self):
        with (
            patch.object(converter.os.path, 'exists', side_effect=[False, False]),
            patch.object(converter.os, 'remove') as remove,
            patch.object(converter.subprocess, 'run'),
        ):
            self.converter.convert_file('/music/song.aac')
        remove.assert_not_called()

    def test_a_failing_ffmpeg_keeps_the_original(self):
        with (
            patch.object(converter.os.path, 'exists', return_value=False),
            patch.object(converter.os, 'remove') as remove,
            patch.object(converter.subprocess, 'run', side_effect=subprocess.CalledProcessError(1, 'ffmpeg')),
        ):
            self.converter.convert_file('/music/song.aac')
        remove.assert_not_called()


class CleanupTempFileTest(ConverterTestCase):
    def test_an_old_temp_file_is_removed(self):
        with (
            patch.object(converter.time, 'time', return_value=1_000_000),
            patch.object(converter.os.path, 'getmtime', return_value=1_000_000 - 25 * 3600),
            patch.object(converter.os, 'remove') as remove,
        ):
            self.converter.cleanup_temp_file('/music/song.temp.m4a')
        remove.assert_called_once_with('/music/song.temp.m4a')

    def test_a_fresh_temp_file_is_kept(self):
        with (
            patch.object(converter.time, 'time', return_value=1_000_000),
            patch.object(converter.os.path, 'getmtime', return_value=1_000_000 - 60),
            patch.object(converter.os, 'remove') as remove,
        ):
            self.converter.cleanup_temp_file('/music/song.temp.m4a')
        remove.assert_not_called()

    def test_the_maximum_age_is_configurable(self):
        converter_with_short_ttl = Converter(max_age_hours=1)
        with (
            patch.object(converter.time, 'time', return_value=1_000_000),
            patch.object(converter.os.path, 'getmtime', return_value=1_000_000 - 2 * 3600),
            patch.object(converter.os, 'remove') as remove,
        ):
            converter_with_short_ttl.cleanup_temp_file('/music/song.temp.m4a')
        remove.assert_called_once()

    def test_a_file_that_disappeared_is_only_a_warning(self):
        with (
            patch.object(converter.os.path, 'getmtime', side_effect=FileNotFoundError),
            self.assertLogs(level='WARNING'),
        ):
            self.converter.cleanup_temp_file('/music/gone.temp.m4a')


if __name__ == '__main__':
    unittest.main()
