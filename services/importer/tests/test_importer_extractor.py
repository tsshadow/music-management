import unittest
from unittest.mock import MagicMock, patch

from services.importer import extractor
from services.importer.extractor import Extractor

# Captured before patoolib is patched away: `except patoolib.util.PatoolError` needs a
# real exception class, which a bare MagicMock attribute is not.
PATOOL_ERROR = extractor.patoolib.util.PatoolError


class ExtractorTest(unittest.TestCase):
    def setUp(self):
        settings = MagicMock(import_folder_path='/import', delimiter='/')
        patcher = patch.object(extractor, 'Settings', return_value=settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.extractor = Extractor()

    def run_with(self, entries, dry_run=False, extract_side_effect=None, remove_side_effect=None):
        with (
            patch.object(extractor, 'listdir', return_value=entries),
            patch.object(extractor, 'isfile', return_value=True),
            patch.object(extractor, 'patoolib') as patool,
            patch.object(extractor.os, 'remove', side_effect=remove_side_effect) as remove,
        ):
            patool.util.PatoolError = PATOOL_ERROR
            if extract_side_effect is not None:
                patool.extract_archive.side_effect = extract_side_effect
            self.extractor.run(dry_run=dry_run)
            return patool, remove

    def test_every_archive_is_extracted_and_then_deleted(self):
        patool, remove = self.run_with(['a.zip', 'b.rar'])
        self.assertEqual(patool.extract_archive.call_count, 2)
        self.assertEqual(remove.call_count, 2)
        self.assertEqual(patool.extract_archive.call_args.kwargs, {'outdir': '/import', 'interactive': False})

    def test_a_dry_run_neither_extracts_nor_deletes(self):
        patool, remove = self.run_with(['a.zip'], dry_run=True)
        patool.extract_archive.assert_not_called()
        remove.assert_not_called()

    def test_directories_are_not_treated_as_archives(self):
        with (
            patch.object(extractor, 'listdir', return_value=['a-folder']),
            patch.object(extractor, 'isfile', return_value=False),
            patch.object(extractor, 'patoolib') as patool,
        ):
            self.extractor.run()
        patool.extract_archive.assert_not_called()

    def test_an_unreadable_import_folder_ends_the_step_quietly(self):
        with (
            patch.object(extractor, 'listdir', side_effect=OSError('no such folder')),
            patch.object(extractor, 'patoolib') as patool,
        ):
            self.extractor.run()
        patool.extract_archive.assert_not_called()

    def test_a_corrupt_archive_does_not_stop_the_remaining_files(self):
        error = PATOOL_ERROR('bad archive')
        # Three attempts on the bad archive: patool's own choice plus both fallbacks.
        patool, remove = self.run_with(['bad.zip', 'good.zip'], extract_side_effect=[error, error, error, None])
        self.assertEqual(patool.extract_archive.call_count, 4)
        self.assertEqual(remove.call_count, 1)

    def test_the_first_attempt_never_names_a_program(self):
        patool, _ = self.run_with(['a.zip'])
        self.assertEqual(patool.extract_archive.call_args.kwargs, {'outdir': '/import', 'interactive': False})

    def test_a_rar_the_default_backend_cannot_read_is_retried_with_unar(self):
        error = PATOOL_ERROR('Pathname cannot be converted from UTF-16BE to current locale')
        patool, _ = self.run_with(['pack.rar'], extract_side_effect=[error, None])
        self.assertEqual(patool.extract_archive.call_count, 2)
        self.assertEqual(patool.extract_archive.call_args.kwargs['program'], 'unar')

    def test_the_archive_is_deleted_when_a_fallback_backend_succeeds(self):
        error = PATOOL_ERROR('bad archive')
        _, remove = self.run_with(['pack.rar'], extract_side_effect=[error, None])
        remove.assert_called_once_with('/import/pack.rar')

    def test_the_chain_stops_at_the_first_backend_that_works(self):
        error = PATOOL_ERROR('bad archive')
        patool, _ = self.run_with(['pack.rar'], extract_side_effect=[error, None])
        programs = [call.kwargs.get('program') for call in patool.extract_archive.call_args_list]
        self.assertNotIn('7z', programs)

    def test_seven_zip_is_tried_when_unar_also_fails(self):
        error = PATOOL_ERROR('bad archive')
        patool, _ = self.run_with(['pack.rar'], extract_side_effect=[error, error, None])
        programs = [call.kwargs.get('program') for call in patool.extract_archive.call_args_list]
        self.assertEqual(programs, [None, 'unar', '7z'])

    def test_an_archive_no_backend_can_read_is_left_on_disk(self):
        error = PATOOL_ERROR('bad archive')
        with self.assertLogs(level='ERROR') as logs:
            patool, remove = self.run_with(['pack.rar'], extract_side_effect=[error, error, error])
        self.assertEqual(patool.extract_archive.call_count, 3)
        remove.assert_not_called()
        message = '\n'.join(logs.output)
        self.assertIn('every backend', message)
        self.assertIn('default:', message)
        self.assertIn('unar:', message)
        self.assertIn('7z:', message)

    def test_an_unexpected_failure_is_not_retried_with_another_backend(self):
        patool, remove = self.run_with(['a.zip'], extract_side_effect=RuntimeError('boom'))
        self.assertEqual(patool.extract_archive.call_count, 1)
        remove.assert_not_called()

    def test_a_file_that_cannot_be_deleted_does_not_stop_the_run(self):
        patool, remove = self.run_with(['a.zip', 'b.zip'], remove_side_effect=OSError('read only'))
        self.assertEqual(remove.call_count, 2)

    def test_an_unexpected_failure_does_not_stop_the_run(self):
        patool, remove = self.run_with(['a.zip', 'b.zip'], extract_side_effect=RuntimeError('boom'))
        self.assertEqual(patool.extract_archive.call_count, 2)


if __name__ == '__main__':
    unittest.main()
