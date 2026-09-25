import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from services.importer import extractor
from services.importer.extractor import Extractor, is_later_volume, sibling_volumes
from services.importer.settle import STAGING_PREFIX

pytestmark = pytest.mark.mock_base('patoolib')

# Captured before patoolib is patched away: `except patoolib.util.PatoolError` needs a
# real exception class, which a bare MagicMock attribute is not.
PATOOL_ERROR = extractor.patoolib.util.PatoolError


def unpack(archive, outdir, **_kwargs):
    """What a working backend does: a release folder named after the archive, holding a track."""
    release = os.path.join(outdir, os.path.splitext(os.path.basename(archive))[0])
    os.makedirs(release, exist_ok=True)
    with open(os.path.join(release, '01-track.mp3'), 'w', encoding='utf-8') as handle:
        handle.write('audio')


class ExtractorHarness(unittest.TestCase):
    """The extract step against a real import folder, with only patool replaced."""

    def setUp(self):
        # pylint does not know enterContext closes the directory at the end of the test.
        self.root = self.enterContext(TemporaryDirectory())  # pylint: disable=consider-using-with
        settings = MagicMock(import_folder_path=self.root, delimiter='/')
        patcher = patch.object(extractor, 'Settings', return_value=settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.extractor = Extractor()

    def touch(self, *names):
        for name in names:
            with open(os.path.join(self.root, name), 'w', encoding='utf-8') as handle:
                handle.write('archive')

    def run_with(self, entries, dry_run=False, extract_side_effect=None, remove_side_effect=None):
        """`remove` is the quarantine call: a successful extract parks the archive.

        It used to be `os.remove`. The archive is the only pristine copy of a label
        release there will ever be, and extraction succeeding says nothing about the
        release surviving the renamer and the mover -- so it is moved aside for the
        retention window instead of deleted on the spot.

        `extract_side_effect` follows mock semantics, except that a None in a list means
        "this attempt worked" and unpacks a release like a real backend would.
        """
        self.touch(*entries)
        outcomes = list(extract_side_effect) if isinstance(extract_side_effect, list) else None

        def extract(archive, outdir, **kwargs):
            outcome = outcomes.pop(0) if outcomes is not None else extract_side_effect
            if isinstance(outcome, BaseException):
                raise outcome
            unpack(archive, outdir, **kwargs)

        with (
            patch.object(extractor, 'patoolib') as patool,
            patch.object(extractor.Quarantine, 'put', side_effect=remove_side_effect) as remove,
        ):
            patool.util.PatoolError = PATOOL_ERROR
            patool.extract_archive.side_effect = extract
            self.extractor.run(dry_run=dry_run)
            return patool, remove

    def entries(self):
        return sorted(os.listdir(self.root))

    def staging_dirs(self):
        return [name for name in self.entries() if name.startswith(STAGING_PREFIX)]

    def outdirs(self, patool):
        return [call.kwargs['outdir'] for call in patool.extract_archive.call_args_list]


class ExtractorTest(ExtractorHarness):
    """What the step does with the archives it finds."""

    def test_every_archive_is_extracted_and_then_quarantined(self):
        patool, remove = self.run_with(['a.zip', 'b.rar'])
        self.assertEqual(patool.extract_archive.call_count, 2)
        self.assertEqual(remove.call_count, 2)
        self.assertEqual(self.entries(), ['a', 'a.zip', 'b', 'b.rar'])

    def test_a_dry_run_neither_extracts_nor_quarantines(self):
        patool, remove = self.run_with(['a.zip'], dry_run=True)
        patool.extract_archive.assert_not_called()
        remove.assert_not_called()

    def test_directories_are_not_treated_as_archives(self):
        os.makedirs(os.path.join(self.root, 'a-folder'))
        with patch.object(extractor, 'patoolib') as patool:
            self.extractor.run()
        patool.extract_archive.assert_not_called()

    def test_a_download_still_in_flight_is_not_opened(self):
        """The 2026-09-16 case: five `.rar.crdownload` files the browser still owned.

        patool identifies by content, so a partial RAR that already has a readable
        header would extract truncated and the source would be quarantined out from
        under the writer. Every one of those archives imported fine on the next cycle
        under its final name.
        """
        patool, remove = self.run_with(['HC-2026-WEEK-37-FLAC.rar.crdownload'])
        patool.extract_archive.assert_not_called()
        remove.assert_not_called()

    def test_every_in_flight_suffix_is_skipped_and_nothing_else_is(self):
        patool, _ = self.run_with(['a.crdownload', 'b.part', 'c.partial', 'd.tmp', 'keep.rar', 'also.crdownload.rar'])
        opened = sorted(os.path.basename(call.args[0]) for call in patool.extract_archive.call_args_list)
        self.assertEqual(opened, ['also.crdownload.rar', 'keep.rar'])

    def test_a_skipped_download_is_reported_without_an_error(self):
        with self.assertLogs(level='INFO') as logs:
            self.run_with(['pack.rar.crdownload', 'keep.rar'])
        message = '\n'.join(logs.output)
        self.assertIn('still in flight', message)
        self.assertIn('pack.rar.crdownload', message)
        self.assertNotIn('ERROR', message)

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
        self.assertNotIn('program', patool.extract_archive.call_args.kwargs)
        self.assertFalse(patool.extract_archive.call_args.kwargs['interactive'])

    def test_a_rar_the_default_backend_cannot_read_is_retried_with_unar(self):
        error = PATOOL_ERROR('Pathname cannot be converted from UTF-16BE to current locale')
        patool, _ = self.run_with(['pack.rar'], extract_side_effect=[error, None])
        self.assertEqual(patool.extract_archive.call_count, 2)
        self.assertEqual(patool.extract_archive.call_args.kwargs['program'], 'unar')

    def test_the_archive_is_quarantined_when_a_fallback_backend_succeeds(self):
        error = PATOOL_ERROR('bad archive')
        _, remove = self.run_with(['pack.rar'], extract_side_effect=[error, None])
        remove.assert_called_once_with(os.path.join(self.root, 'pack.rar'), 'extracted-archive')

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

    def test_a_file_that_cannot_be_quarantined_does_not_stop_the_run(self):
        patool, remove = self.run_with(['a.zip', 'b.zip'], remove_side_effect=OSError('read only'))
        self.assertEqual(remove.call_count, 2)

    def test_an_unexpected_failure_does_not_stop_the_run(self):
        patool, remove = self.run_with(['a.zip', 'b.zip'], extract_side_effect=RuntimeError('boom'))
        self.assertEqual(patool.extract_archive.call_count, 2)


class StagedExtractionTest(ExtractorHarness):
    """Every backend extracts into a staging folder; only a complete result reaches the import folder.

    The documented case: unrar-free gave up after 13 of the 44 releases in a weekly pack.
    Extracting straight into the import folder left those 13 there, the fallback
    extracted all 44 on top of them -- 7z's `-aou` renaming each collision to
    `name_1.mp3` -- and the same cycle's flattener, renamer and mover placed the result.
    """

    def half_then_fail(self, archive, outdir, **_kwargs):
        """unrar-free on a name it cannot convert: part of the archive, then an error."""
        release = os.path.join(outdir, 'Pack', 'Release-13')
        os.makedirs(release)
        with open(os.path.join(release, '01-track.mp3'), 'w', encoding='utf-8') as handle:
            handle.write('audio')
        raise PATOOL_ERROR('Pathname cannot be converted from UTF-16BE to current locale')

    def run_with_backends(self, *backends):
        """Run one archive through the step, each attempt handled by the next function given."""
        self.touch('pack.rar')
        calls = list(backends)
        with (
            patch.object(extractor, 'patoolib') as patool,
            patch.object(extractor.Quarantine, 'put') as put,
        ):
            patool.util.PatoolError = PATOOL_ERROR
            patool.extract_archive.side_effect = lambda archive, outdir, **kw: calls.pop(0)(archive, outdir, **kw)
            self.extractor.run()
        return patool, put

    def test_a_backend_that_fails_halfway_leaves_nothing_in_the_import_folder(self):
        failed = PATOOL_ERROR('bad archive')

        def fail(*_args, **_kwargs):
            raise failed

        _, put = self.run_with_backends(self.half_then_fail, fail, fail)

        self.assertEqual(self.entries(), ['pack.rar'])
        put.assert_not_called()

    def test_the_fallback_starts_from_an_empty_folder_and_nothing_is_doubled(self):
        patool, put = self.run_with_backends(self.half_then_fail, unpack)

        self.assertEqual(self.entries(), ['pack', 'pack.rar'])
        self.assertEqual(os.listdir(os.path.join(self.root, 'pack')), ['01-track.mp3'])
        put.assert_called_once_with(os.path.join(self.root, 'pack.rar'), 'extracted-archive')
        first, second = self.outdirs(patool)
        self.assertNotEqual(first, second)

    def test_every_attempt_writes_beside_the_archive_not_into_the_import_folder(self):
        patool, _ = self.run_with(['a.zip'])
        (outdir,) = self.outdirs(patool)
        self.assertEqual(os.path.dirname(outdir), self.root)
        self.assertTrue(os.path.basename(outdir).startswith(STAGING_PREFIX))
        self.assertEqual(self.staging_dirs(), [])

    def test_an_unexpected_failure_leaves_no_staging_folder(self):
        self.run_with(['a.zip'], extract_side_effect=RuntimeError('boom'))
        self.assertEqual(self.entries(), ['a.zip'])

    def test_a_name_taken_by_something_else_keeps_the_archive_for_a_human(self):
        os.makedirs(os.path.join(self.root, 'a'))
        with open(os.path.join(self.root, 'a', '01-track.mp3'), 'w', encoding='utf-8') as handle:
            handle.write('a different recording')

        with self.assertLogs(level='WARNING') as logs:
            _, remove = self.run_with(['a.zip'])

        remove.assert_not_called()
        self.assertEqual(self.entries(), ['a', 'a.zip'])
        with open(os.path.join(self.root, 'a', '01-track.mp3'), encoding='utf-8') as handle:
            self.assertEqual(handle.read(), 'a different recording')
        self.assertIn('manual intervention', '\n'.join(logs.output))

    def test_a_name_taken_by_the_same_release_is_not_a_conflict(self):
        unpack(os.path.join(self.root, 'a.zip'), self.root)

        _, remove = self.run_with(['a.zip'])

        remove.assert_called_once()
        self.assertEqual(self.entries(), ['a', 'a.zip'])

    def test_an_archive_that_extracts_to_nothing_stays(self):
        _, put = self.run_with_backends(lambda *_args, **_kwargs: None)

        put.assert_not_called()
        self.assertEqual(self.entries(), ['pack.rar'])

    def test_a_staging_folder_a_killed_run_left_behind_is_removed(self):
        leftover = os.path.join(self.root, STAGING_PREFIX + 'killed')
        os.makedirs(os.path.join(leftover, 'Half-A-Release'))

        self.run_with([])

        self.assertEqual(self.entries(), [])

    def test_a_dry_run_leaves_a_staging_folder_alone(self):
        leftover = os.path.join(self.root, STAGING_PREFIX + 'killed')
        os.makedirs(leftover)

        self.run_with([], dry_run=True)

        self.assertEqual(self.staging_dirs(), [STAGING_PREFIX + 'killed'])


class SplitRarVolumeTest(ExtractorHarness):
    """A multi-volume RAR is extracted from its first volume and leaves as one set.

    There is no `rar` binary in the test image to build a real set, so patool is the stub
    it is everywhere in this file, and what is asserted is which volume gets opened and
    what gets parked afterwards -- the extraction of the set itself is unrar's job.
    """

    def test_only_the_first_volume_is_opened_and_the_set_is_quarantined_together(self):
        patool, put = self.run_with(['set.part1.rar', 'set.part2.rar', 'set.part3.rar'])

        opened = [os.path.basename(call.args[0]) for call in patool.extract_archive.call_args_list]
        self.assertEqual(opened, ['set.part1.rar'])
        parked = [os.path.basename(call.args[0]) for call in put.call_args_list]
        self.assertEqual(parked, ['set.part1.rar', 'set.part2.rar', 'set.part3.rar'])

    def test_the_old_naming_scheme_is_a_set_too(self):
        patool, put = self.run_with(['set.rar', 'set.r00', 'set.r01'])

        opened = [os.path.basename(call.args[0]) for call in patool.extract_archive.call_args_list]
        self.assertEqual(opened, ['set.rar'])
        parked = [os.path.basename(call.args[0]) for call in put.call_args_list]
        self.assertEqual(parked, ['set.rar', 'set.r00', 'set.r01'])

    def test_a_set_that_fails_to_extract_stays_whole(self):
        error = PATOOL_ERROR('missing volume')
        _, put = self.run_with(['set.part1.rar', 'set.part2.rar'], extract_side_effect=[error, error, error])

        put.assert_not_called()
        self.assertEqual(self.entries(), ['set.part1.rar', 'set.part2.rar'])

    def test_a_set_whose_later_volume_is_still_downloading_waits(self):
        patool, put = self.run_with(['set.part1.rar', 'set.part2.rar.crdownload'])

        patool.extract_archive.assert_not_called()
        put.assert_not_called()

    def test_another_set_is_not_quarantined_with_it(self):
        _, put = self.run_with(['one.part1.rar', 'one.part2.rar', 'two.part1.rar', 'two.part2.rar'])

        parked = sorted(os.path.basename(call.args[0]) for call in put.call_args_list)
        self.assertEqual(parked, ['one.part1.rar', 'one.part2.rar', 'two.part1.rar', 'two.part2.rar'])
        self.assertEqual(put.call_count, 4)


class VolumeNameTest(unittest.TestCase):
    """Which file names belong to which RAR set."""

    def test_later_volumes_of_both_schemes_are_recognised(self):
        self.assertTrue(is_later_volume('set.part2.rar'))
        self.assertTrue(is_later_volume('set.part02.RAR'))
        self.assertTrue(is_later_volume('set.r00'))
        self.assertTrue(is_later_volume('set.s12'))

    def test_first_volumes_and_ordinary_archives_are_not(self):
        self.assertFalse(is_later_volume('set.part1.rar'))
        self.assertFalse(is_later_volume('set.part001.rar'))
        self.assertFalse(is_later_volume('set.rar'))
        self.assertFalse(is_later_volume('release.zip'))
        self.assertFalse(is_later_volume('track.mp3'))

    def test_siblings_are_matched_on_the_whole_base_name(self):
        entries = ['a.part1.rar', 'a.part2.rar', 'ab.part2.rar', 'a.rar', 'a.r00']
        self.assertEqual(sibling_volumes('a.part1.rar', entries), ['a.part2.rar'])
        self.assertEqual(sibling_volumes('a.rar', entries), ['a.r00'])
        self.assertEqual(sibling_volumes('release.zip', entries), [])


if __name__ == '__main__':
    unittest.main()
