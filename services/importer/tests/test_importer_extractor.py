import logging
import os
import subprocess
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from services.importer import extractor
from services.importer.conflict_store import FileProblemTracker
from services.importer.extractor import Extractor, is_later_volume, sibling_volumes
from services.importer.settle import STAGING_PREFIX

pytestmark = pytest.mark.mock_base('patoolib')

# Captured before patoolib is patched away: `except patoolib.util.PatoolError` needs a
# real exception class, which a bare MagicMock attribute is not.
PATOOL_ERROR = extractor.patoolib.util.PatoolError


def signature_for(name):
    """The first bytes a real archive of this name starts with, so it passes the content check."""
    lower = name.lower()
    if lower.endswith('.zip'):
        return b'PK\x03\x04'
    if lower.endswith('.rar'):
        return b'Rar!\x1a\x07\x00'
    return b''


class FakeProblemStore:
    """`importer_conflicts` as far as the extractor sees it; outlives an Extractor like the database does."""

    def __init__(self):
        self.rows: dict[str, dict] = {}

    def snapshot(self, step):
        return {key: row['fingerprint'] for key, row in self.rows.items() if row['step'] == step}

    def record(self, key, step, source, target, fingerprint, reason=None):
        self.rows[key] = {
            'step': step,
            'source': source,
            'target': target,
            'fingerprint': fingerprint,
            'reason': reason,
        }

    def touch(self, key):
        pass

    def forget(self, key):
        self.rows.pop(key, None)


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
        settings = MagicMock(
            import_folder_path=self.root, delimiter='/', import_extract_max_gb=50, import_extract_min_free_gb=0
        )
        self.settings = settings
        patcher = patch.object(extractor, 'Settings', return_value=settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = FakeProblemStore()
        self.extractor = self.new_extractor()

    def new_extractor(self):
        """An extractor as a fresh importer process would build it, sharing the one database."""
        with patch.object(extractor, 'FileProblemTracker', lambda: FileProblemTracker(self.store)):
            return Extractor()

    def touch(self, *names, content=None):
        """Create files in the import folder; an archive name gets its real signature."""
        for name in names:
            with open(os.path.join(self.root, name), 'wb') as handle:
                handle.write(content if content is not None else signature_for(name) + b'archive')

    def run_with(self, entries, dry_run=False, extract_side_effect=None, remove_side_effect=None):
        """`remove` is the quarantine call: a successful extract parks the archive.

        It used to be `os.remove`. The archive is the only pristine copy of a label
        release there will ever be, and extraction succeeding says nothing about the
        release surviving the renamer and the mover -- so it is moved aside for the
        retention window instead of deleted on the spot.

        `extract_side_effect` follows mock semantics, except that a None in a list means
        "this attempt worked" and unpacks a release like a real backend would, and a
        function stands in for the backend itself.
        """
        self.touch(*entries)
        outcomes = list(extract_side_effect) if isinstance(extract_side_effect, list) else None

        def extract(archive, outdir, **kwargs):
            outcome = outcomes.pop(0) if outcomes is not None else extract_side_effect
            if isinstance(outcome, BaseException):
                raise outcome
            if callable(outcome):
                outcome(archive, outdir, **kwargs)
                return
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
        with self.assertLogs(level='WARNING') as logs:
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
        _patool, remove = self.run_with(['a.zip', 'b.zip'], remove_side_effect=OSError('read only'))
        self.assertEqual(remove.call_count, 2)

    def test_an_unexpected_failure_does_not_stop_the_run(self):
        patool, _remove = self.run_with(['a.zip', 'b.zip'], extract_side_effect=RuntimeError('boom'))
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

    def test_an_archive_with_a_link_out_of_its_folder_stays(self):
        # A release is files and folders. A link to a place outside would come into the import
        # folder with the release, and the tagger would later write through it (issue #217).
        outside = self.enterContext(TemporaryDirectory())  # pylint: disable=consider-using-with

        def link_out(archive, outdir, **kwargs):
            unpack(archive, outdir, **kwargs)
            os.symlink(outside, os.path.join(outdir, 'pack', 'cover'))

        _, put = self.run_with_backends(link_out)

        put.assert_not_called()
        self.assertEqual(self.entries(), ['pack.rar'])
        self.assertEqual([row['reason'] for row in self.store.rows.values()], ['extraction-unsafe'])

    def test_a_link_inside_the_release_is_fine(self):
        def link_in(archive, outdir, **kwargs):
            unpack(archive, outdir, **kwargs)
            os.symlink('01-track.mp3', os.path.join(outdir, 'pack', 'same-track.mp3'))

        _, put = self.run_with_backends(link_in)

        put.assert_called_once()
        self.assertEqual(self.entries(), ['pack', 'pack.rar'])

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


class NonArchiveTest(ExtractorHarness):
    """Bug report 119: what is not an archive, or cannot be extracted, is recorded once and left alone.

    On 2026-09-27 two `.mp4` videos a browser download left in the import folder were handed
    to patool on every cycle -- two WARNINGs and an ERROR per file per cycle, 218 and 109 of
    them per file in twelve hours.
    """

    def cycle(self, extract_side_effect=None, instance=None):
        """One run of the step with patool stubbed; returns (patool, quarantine put, warnings)."""
        outcomes = list(extract_side_effect) if isinstance(extract_side_effect, list) else None

        def extract(archive, outdir, **kwargs):
            outcome = outcomes.pop(0) if outcomes is not None else extract_side_effect
            if isinstance(outcome, BaseException):
                raise outcome
            unpack(archive, outdir, **kwargs)

        with (
            patch.object(extractor, 'patoolib') as patool,
            patch.object(extractor.Quarantine, 'put') as put,
            self.assertLogs(level='DEBUG') as logs,
        ):
            patool.util.PatoolError = PATOOL_ERROR
            patool.extract_archive.side_effect = extract
            (instance or self.extractor).run()
        warnings = [record.getMessage() for record in logs.records if record.levelno >= logging.WARNING]
        return patool, put, warnings

    def test_a_video_is_never_extracted_and_warned_about_once_across_two_cycles(self):
        self.touch('some-download-p1080.mp4', content=b'\x00\x00\x00\x18ftypmp42')

        first, _, first_warnings = self.cycle()
        second, _, second_warnings = self.cycle()

        first.extract_archive.assert_not_called()
        second.extract_archive.assert_not_called()
        self.assertEqual(len(first_warnings), 1)
        self.assertIn('not music: video file', first_warnings[0])
        self.assertEqual(second_warnings, [])
        self.assertEqual(self.entries(), ['some-download-p1080.mp4'])
        (row,) = self.store.rows.values()
        self.assertEqual(row['step'], 'extractor')
        self.assertEqual(row['reason'], 'not-music-video')
        self.assertEqual(row['source'], os.path.join(self.root, 'some-download-p1080.mp4'))

    def test_a_restart_does_not_warn_about_a_standing_file_again(self):
        self.touch('clip.mp4', content=b'video')
        self.cycle()

        _, _, warnings = self.cycle(instance=self.new_extractor())

        self.assertEqual(warnings, [])

    def test_a_corrupt_zip_is_warned_about_once_and_parked(self):
        error = PATOOL_ERROR('bad archive')
        self.touch('broken.zip')

        first, first_put, first_warnings = self.cycle(extract_side_effect=[error, error, error])
        second, second_put, second_warnings = self.cycle(extract_side_effect=[error, error, error])

        self.assertEqual(first.extract_archive.call_count, 3)
        second.extract_archive.assert_not_called()
        first_put.assert_not_called()
        second_put.assert_not_called()
        self.assertEqual(len(first_warnings), 1)
        self.assertIn('every backend failed', first_warnings[0])
        self.assertEqual(second_warnings, [])
        self.assertEqual(self.entries(), ['broken.zip'])
        (row,) = self.store.rows.values()
        self.assertEqual(row['reason'], 'extraction-failed')

    def test_a_parked_archive_is_tried_again_once_it_changes_on_disk(self):
        error = PATOOL_ERROR('bad archive')
        self.touch('pack.zip')
        self.cycle(extract_side_effect=[error, error, error])
        self.touch('pack.zip', content=b'PK\x03\x04' + b'the full download this time')

        patool, put, _ = self.cycle()

        patool.extract_archive.assert_called_once()
        put.assert_called_once_with(os.path.join(self.root, 'pack.zip'), 'extracted-archive')
        self.assertEqual(self.store.rows, {})

    def test_a_normal_zip_still_extracts_and_leaves_nothing_standing(self):
        self.touch('release.zip')

        patool, put, warnings = self.cycle()

        patool.extract_archive.assert_called_once()
        put.assert_called_once_with(os.path.join(self.root, 'release.zip'), 'extracted-archive')
        self.assertEqual(warnings, [])
        self.assertEqual(self.store.rows, {})
        self.assertIn('release', self.entries())

    def test_a_file_named_like_an_archive_without_its_signature_is_not_opened(self):
        self.touch('error-page.zip', content=b'<html>403 Forbidden</html>')

        patool, _, warnings = self.cycle()

        patool.extract_archive.assert_not_called()
        self.assertEqual(len(warnings), 1)
        (row,) = self.store.rows.values()
        self.assertEqual(row['reason'], 'not-an-archive')

    def test_a_file_that_is_removed_is_forgotten(self):
        self.touch('clip.mp4', content=b'video')
        self.cycle()
        os.remove(os.path.join(self.root, 'clip.mp4'))

        self.cycle()

        self.assertEqual(self.store.rows, {})

    def test_hidden_and_housekeeping_files_are_passed_over_silently(self):
        self.touch('.DS_Store', 'Thumbs.db', content=b'junk')

        patool, _, warnings = self.cycle()

        patool.extract_archive.assert_not_called()
        self.assertEqual(warnings, [])
        self.assertEqual(self.store.rows, {})

    def test_an_archive_whose_folder_name_is_taken_is_warned_about_once(self):
        os.makedirs(os.path.join(self.root, 'a'))
        with open(os.path.join(self.root, 'a', '01-track.mp3'), 'w', encoding='utf-8') as handle:
            handle.write('a different recording')
        self.touch('a.zip')

        _, first_put, first_warnings = self.cycle()
        second, _, second_warnings = self.cycle()

        first_put.assert_not_called()
        self.assertEqual(len(first_warnings), 1)
        second.extract_archive.assert_not_called()
        self.assertEqual(second_warnings, [])
        (row,) = self.store.rows.values()
        self.assertEqual(row['reason'], 'extraction-name-taken')

    def test_an_archive_that_extracts_to_nothing_is_recorded_as_such(self):
        self.touch('empty.zip')

        with (
            patch.object(extractor, 'patoolib') as patool,
            patch.object(extractor.Quarantine, 'put') as put,
            self.assertLogs(level='WARNING') as logs,
        ):
            patool.util.PatoolError = PATOOL_ERROR
            patool.extract_archive.side_effect = lambda *_args, **_kwargs: None
            self.extractor.run()

        put.assert_not_called()
        self.assertEqual(len(logs.records), 1)
        (row,) = self.store.rows.values()
        self.assertEqual(row['reason'], 'extraction-empty')

    def test_an_archive_whose_folder_name_is_freed_is_extracted_again(self):
        taken = os.path.join(self.root, 'a')
        os.makedirs(taken)
        with open(os.path.join(taken, '01-track.mp3'), 'w', encoding='utf-8') as handle:
            handle.write('a different recording')
        self.touch('a.zip')
        self.cycle()
        os.remove(os.path.join(taken, '01-track.mp3'))
        os.rmdir(taken)
        # A coarse filesystem clock could leave the folder mtime where it was.
        stat = os.stat(self.root)
        os.utime(self.root, ns=(stat.st_atime_ns, stat.st_mtime_ns + 1_000_000_000))

        patool, put, warnings = self.cycle()

        patool.extract_archive.assert_called_once()
        put.assert_called_once_with(os.path.join(self.root, 'a.zip'), 'extracted-archive')
        self.assertEqual(warnings, [])
        self.assertEqual(self.store.rows, {})

    def test_a_dry_run_records_nothing(self):
        self.touch('clip.mp4', content=b'video')

        with patch.object(extractor, 'patoolib'), self.assertLogs(level='WARNING'):
            self.extractor.run(dry_run=True)

        self.assertEqual(self.store.rows, {})


class ExtractionBudgetTest(ExtractorHarness):
    """An archive that expands past the budget is stopped while it extracts (issue #231)."""

    def setUp(self):
        super().setUp()
        # 64 "GB" of 1 KiB each: a budget a test can pass in a fraction of a second.
        patcher = patch.object(extractor, 'GIB', 1024)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.settings.import_extract_max_gb = 64

    def test_a_backend_that_writes_past_the_budget_is_killed_and_the_archive_stays(self):
        self.touch('Unrelated Release - 01.mp3')
        # Started before the extraction: the importer's own child, which the stop must spare.
        bystander = subprocess.Popen(['sleep', '30'])  # pylint: disable=consider-using-with
        self.addCleanup(bystander.wait)
        self.addCleanup(bystander.kill)

        def bomb(_archive, outdir, **_kwargs):
            # A real backend: a child process that writes until something stops it.
            result = subprocess.run(
                ['sh', '-c', 'while :; do head -c 65536 /dev/zero >> "$0/bomb.bin"; done', outdir], check=False
            )
            raise PATOOL_ERROR(f'Command exited with status {result.returncode}')

        patool, remove = self.run_with(['bomb.zip'], extract_side_effect=bomb)

        self.assertEqual(patool.extract_archive.call_count, 1, 'another backend would write the same bytes')
        remove.assert_not_called()
        self.assertEqual(self.entries(), ['Unrelated Release - 01.mp3', 'bomb.zip'])
        self.assertIsNone(bystander.poll(), 'a child started before the extraction was killed')
        (row,) = [row for row in self.store.rows.values() if row['source'].endswith('bomb.zip')]
        self.assertEqual(row['reason'], 'extraction-too-large')
        self.assertIn('passed 65536 bytes', row['target'])

    def test_an_archive_within_the_budget_extracts(self):
        patool, remove = self.run_with(['small.zip'])

        patool.extract_archive.assert_called_once()
        remove.assert_called_once()
        self.assertEqual(self.entries(), ['small', 'small.zip'])


class ClassifyTest(unittest.TestCase):
    """Which files the extract step opens: archive extension and archive signature, both."""

    def setUp(self):
        self.root = self.enterContext(TemporaryDirectory())  # pylint: disable=consider-using-with

    def kind(self, name, content):
        path = os.path.join(self.root, name)
        with open(path, 'wb') as handle:
            handle.write(content)
        return extractor.classify(path, name)[0]

    def test_real_archives_are_archives(self):
        self.assertEqual(self.kind('a.zip', b'PK\x03\x04rest'), 'archive')
        self.assertEqual(self.kind('a.RAR', b'Rar!\x1a\x07\x01\x00'), 'archive')
        self.assertEqual(self.kind('a.7z', b"7z\xbc\xaf'\x1c"), 'archive')
        self.assertEqual(self.kind('a.tar.gz', b'\x1f\x8b\x08'), 'archive')
        self.assertEqual(self.kind('a.tar', b'\x00' * 257 + b'ustar\x0000'), 'archive')

    def test_an_archive_extension_alone_is_not_enough(self):
        self.assertEqual(self.kind('a.rar', b'PK\x03\x04'), 'not-an-archive')
        self.assertEqual(self.kind('a.tar', b'plain text'), 'not-an-archive')

    def test_an_archive_signature_alone_is_not_enough(self):
        self.assertEqual(self.kind('video.mp4', b'PK\x03\x04'), 'not-music-video')

    def test_other_files_are_named_by_kind(self):
        self.assertEqual(self.kind('track.flac', b'fLaC'), 'loose-audio')
        self.assertEqual(self.kind('cover.JPG', b'\xff\xd8'), 'not-music-image')
        self.assertEqual(self.kind('info.nfo', b'text'), 'not-music-document')
        self.assertEqual(self.kind('setup.exe', b'MZ'), 'not-music-other')


if __name__ == '__main__':
    unittest.main()
