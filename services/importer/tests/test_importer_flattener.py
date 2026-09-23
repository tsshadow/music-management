import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from services.importer import flattener, settle
from services.importer.flattener import Flattener


class FlattenerTest(unittest.TestCase):
    """
    A weekly pack (a multipack) extracts into a wrapper folder: the releases end up at
    import/<pack>/<release> instead of import/<release>, so the Renamer and the Mover
    never see them. The Flattener lifts those releases back to the import root.
    """

    def setUp(self):
        # Folders made a moment ago count as settled here; the guard has tests of its own.
        self.enterContext(patch.object(settle, 'settle_seconds', return_value=0))
        # pylint does not know enterContext closes the directory at the end of the test.
        self.root = self.enterContext(TemporaryDirectory())  # pylint: disable=consider-using-with
        settings = MagicMock(import_folder_path=self.root, delimiter=os.sep)
        patcher = patch.object(flattener, 'Settings', return_value=settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.flattener = Flattener()

    def make(self, *parts, files=()):
        path = os.path.join(self.root, *parts)
        os.makedirs(path, exist_ok=True)
        for name in files:
            with open(os.path.join(path, name), 'w', encoding='utf-8') as handle:
                handle.write('x')
        return path

    def entries(self):
        return sorted(os.listdir(self.root))

    def test_the_releases_inside_a_wrapper_are_lifted_to_the_import_root(self):
        self.make('HHC-2026-WEEK-33', 'Artist_-_One-(BONKERS084)-WEB-2026', files=['one.mp3'])
        self.make('HHC-2026-WEEK-33', 'Artist_-_Two-(BONKERS085)-WEB-2026', files=['two.mp3'])

        self.flattener.run()

        self.assertEqual(self.entries(), ['Artist_-_One-(BONKERS084)-WEB-2026', 'Artist_-_Two-(BONKERS085)-WEB-2026'])
        self.assertTrue(os.path.isfile(os.path.join(self.root, 'Artist_-_One-(BONKERS084)-WEB-2026', 'one.mp3')))

    def test_a_release_folder_in_the_root_is_left_alone(self):
        self.make('Artist_-_One-(BONKERS084)-WEB-2026', files=['one.mp3'])

        self.flattener.run()

        self.assertEqual(self.entries(), ['Artist_-_One-(BONKERS084)-WEB-2026'])

    def test_a_release_whose_audio_sits_in_a_single_subfolder_is_left_alone(self):
        self.make('Artist_-_Album-(CAT123)-WEB-2026', 'CD1', files=['one.mp3'])

        self.flattener.run()

        self.assertEqual(self.entries(), ['Artist_-_Album-(CAT123)-WEB-2026'])

    def test_a_wrapper_around_a_wrapper_is_flattened_all_the_way(self):
        self.make('outer', 'HHC-2026-WEEK-33', 'Artist_-_One-(BONKERS084)-WEB-2026', files=['one.mp3'])
        self.make('outer', 'HHC-2026-WEEK-33', 'Artist_-_Two-(BONKERS085)-WEB-2026', files=['two.mp3'])

        self.flattener.run()

        self.assertEqual(self.entries(), ['Artist_-_One-(BONKERS084)-WEB-2026', 'Artist_-_Two-(BONKERS085)-WEB-2026'])

    def test_loose_junk_next_to_the_releases_does_not_hide_the_wrapper(self):
        self.make('HHC-2026-WEEK-33', files=['pack.nfo', 'pack.sfv'])
        self.make('HHC-2026-WEEK-33', 'Artist_-_One-(BONKERS084)-WEB-2026', files=['one.mp3'])
        self.make('HHC-2026-WEEK-33', 'Artist_-_Two-(BONKERS085)-WEB-2026', files=['two.mp3'])

        self.flattener.run()

        self.assertEqual(self.entries(), ['Artist_-_One-(BONKERS084)-WEB-2026', 'Artist_-_Two-(BONKERS085)-WEB-2026'])

    def test_a_release_that_already_exists_in_the_root_is_not_overwritten(self):
        self.make('Artist_-_One-(BONKERS084)-WEB-2026', files=['original.mp3'])
        self.make('HHC-2026-WEEK-33', 'Artist_-_One-(BONKERS084)-WEB-2026', files=['duplicate.mp3'])
        self.make('HHC-2026-WEEK-33', 'Artist_-_Two-(BONKERS085)-WEB-2026', files=['two.mp3'])

        self.flattener.run()

        self.assertEqual(
            self.entries(),
            ['Artist_-_One-(BONKERS084)-WEB-2026', 'Artist_-_Two-(BONKERS085)-WEB-2026', 'HHC-2026-WEEK-33'],
        )
        self.assertTrue(os.path.isfile(os.path.join(self.root, 'Artist_-_One-(BONKERS084)-WEB-2026', 'original.mp3')))
        self.assertEqual(
            os.listdir(os.path.join(self.root, 'HHC-2026-WEEK-33')), ['Artist_-_One-(BONKERS084)-WEB-2026']
        )

    def test_the_synology_thumbnail_folder_is_never_flattened(self):
        self.make('@eaDir', 'Artist_-_One-(BONKERS084)-WEB-2026', 'SYNOPHOTO', files=['thumb.jpg'])
        self.make('@eaDir', 'Artist_-_Two-(BONKERS085)-WEB-2026', 'SYNOPHOTO', files=['thumb.jpg'])

        self.flattener.run()

        self.assertEqual(self.entries(), ['@eaDir'])

    def test_a_dry_run_reports_the_move_without_touching_the_disk(self):
        self.make('HHC-2026-WEEK-33', 'Artist_-_One-(BONKERS084)-WEB-2026', files=['one.mp3'])
        self.make('HHC-2026-WEEK-33', 'Artist_-_Two-(BONKERS085)-WEB-2026', files=['two.mp3'])

        self.flattener.run(dry_run=True)

        self.assertEqual(self.entries(), ['HHC-2026-WEEK-33'])

    def test_an_unreadable_import_folder_ends_the_step_quietly(self):
        with patch.object(flattener.os, 'listdir', side_effect=OSError('no such folder')):
            self.flattener.run()

    def test_a_loose_file_in_the_import_root_is_ignored(self):
        with open(os.path.join(self.root, 'leftover.rar'), 'w', encoding='utf-8') as handle:
            handle.write('x')

        self.flattener.run()

        self.assertEqual(self.entries(), ['leftover.rar'])


if __name__ == '__main__':
    unittest.main()
