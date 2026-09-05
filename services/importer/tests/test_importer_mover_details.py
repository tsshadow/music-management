import os
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

from services.tests.connector_fakes import fake_connector
from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()

from services.importer import mover as mover_module
from services.importer.mover import Mover, get_cat_id, post_processing_songs


class CatIdTest(unittest.TestCase):
    def test_a_folder_without_a_space_has_no_catalog_id(self):
        self.assertIsNone(get_cat_id('SCAN123'))

    def test_the_letters_in_front_of_the_number_are_the_catalog_id(self):
        self.assertEqual(get_cat_id('SCAN123 - Release'), 'SCAN')

    def test_underscores_and_dashes_are_ignored(self):
        self.assertEqual(get_cat_id('SCAN_123 - Release'), 'SCAN')
        self.assertEqual(get_cat_id('SCAN-123 - Release'), 'SCAN')

    def test_labels_whose_own_name_contains_digits_are_special_cased(self):
        self.assertEqual(get_cat_id('247HC001 - Release'), '247HC')
        self.assertEqual(get_cat_id('R909012 - Release'), 'R909')
        self.assertEqual(get_cat_id('UNFD123 - Release'), 'UNFD')

    def test_a_first_part_without_three_consecutive_digits_is_used_as_is(self):
        self.assertEqual(get_cat_id('SCAN12 - Release'), 'SCAN12')


class PostProcessingTest(unittest.TestCase):
    def setUp(self):
        reset_database_helpers()

    def test_only_supported_audio_extensions_are_processed(self):
        with (
            patch.object(mover_module.os, 'walk', return_value=[('/eps/x', [], ['a.mp3', 'b.flac', 'cover.jpg'])]),
            patch.object(mover_module.os.path, 'isfile', return_value=True),
            patch.object(mover_module, 'LabelSong') as label_song,
        ):
            post_processing_songs('/eps/x')
        self.assertEqual(label_song.call_count, 2)

    def test_synology_metadata_directories_are_pruned_from_the_walk(self):
        dirs = ['@eaDir', 'disc1']
        with (
            patch.object(mover_module.os, 'walk', return_value=[('/eps/x', dirs, [])]),
            patch.object(mover_module.os.path, 'isfile', return_value=True),
            patch.object(mover_module, 'LabelSong'),
        ):
            post_processing_songs('/eps/x')
        self.assertEqual(dirs, ['disc1'])

    def test_a_path_that_is_not_a_real_file_is_skipped(self):
        with (
            patch.object(mover_module.os, 'walk', return_value=[('/eps/x', [], ['a.mp3'])]),
            patch.object(mover_module.os.path, 'isfile', return_value=False),
            patch.object(mover_module, 'LabelSong') as label_song,
        ):
            post_processing_songs('/eps/x')
        label_song.assert_not_called()

    def test_a_song_that_fails_to_parse_does_not_stop_the_rest(self):
        with (
            patch.object(mover_module.os, 'walk', return_value=[('/eps/x', [], ['a.mp3', 'b.mp3'])]),
            patch.object(mover_module.os.path, 'isfile', return_value=True),
            patch.object(mover_module, 'LabelSong') as label_song,
        ):
            label_song.return_value.parse.side_effect = [RuntimeError('bad tags'), None]
            post_processing_songs('/eps/x')
        self.assertEqual(label_song.call_count, 2)


class MoverTestCase(unittest.TestCase):
    def setUp(self):
        reset_database_helpers()
        self.settings = MagicMock(import_folder_path='/import', eps_folder_path='/eps', delimiter='/')
        self.connector, self.connection = fake_connector()
        self.cursor = self.connection.cursor.return_value.__enter__.return_value
        patches = [
            patch.object(mover_module, 'Settings', return_value=self.settings),
            patch.object(mover_module, 'DatabaseConnector', return_value=self.connector),
        ]
        for p in patches:
            p.start()
            self.addCleanup(p.stop)
        self.mover = Mover()


class GetLabelTest(MoverTestCase):
    def test_the_label_for_a_known_catalog_id_is_returned(self):
        self.cursor.fetchone.return_value = ('Scantraxx',)
        self.assertEqual(self.mover.get_label('SCAN'), 'Scantraxx')

    def test_an_unknown_catalog_id_has_no_label(self):
        self.cursor.fetchone.return_value = None
        self.assertIsNone(self.mover.get_label('NOPE'))

    def test_a_database_error_is_reported_as_no_label(self):
        self.connection.cursor.side_effect = RuntimeError('database gone')
        self.assertIsNone(self.mover.get_label('SCAN'))


class RemoveTest(MoverTestCase):
    def test_the_folder_is_removed_from_the_import_directory(self):
        with patch.object(mover_module.shutil, 'rmtree') as rmtree:
            self.mover.remove('SCAN123 - Release')
        rmtree.assert_called_once_with('/import/SCAN123 - Release')

    def test_a_removal_failure_is_only_logged(self):
        with patch.object(mover_module.shutil, 'rmtree', side_effect=PermissionError('read only')):
            self.mover.remove('SCAN123 - Release')  # must not raise


class MoveFolderTest(MoverTestCase):
    def setUp(self):
        super().setUp()
        self.cursor.fetchone.return_value = ('Scantraxx',)

    def test_a_folder_with_a_known_label_is_moved_into_the_label_directory(self):
        with patch.object(mover_module.shutil, 'move') as move, patch.object(mover_module, 'post_processing_songs'):
            self.mover._move_folder('SCAN123 - Release', 'SCAN', dry_run=False)
        move.assert_called_once_with('/import/SCAN123 - Release', '/eps/Scantraxx/SCAN123 - Release')

    def test_an_unknown_catalog_id_stops_before_moving_anything(self):
        self.cursor.fetchone.return_value = None
        with patch.object(mover_module.shutil, 'move') as move:
            self.mover._move_folder('NOPE123 - Release', 'NOPE', dry_run=False)
        move.assert_not_called()

    def test_an_unknown_catalog_id_is_recorded_as_a_proposal(self):
        self.cursor.fetchone.return_value = None
        self.mover.proposals = MagicMock()

        self.mover._move_folder('NOPE123 - Release', 'NOPE', dry_run=False)

        folder, proposal = self.mover.proposals.record.call_args.args
        self.assertEqual(folder, 'NOPE123 - Release')
        self.assertEqual(proposal.catid, 'NOPE')

    def test_a_dry_run_reports_the_move_without_performing_it(self):
        with (
            patch.object(mover_module.shutil, 'move') as move,
            patch.object(mover_module, 'post_processing_songs') as post,
        ):
            self.mover._move_folder('SCAN123 - Release', 'SCAN', dry_run=True)
        move.assert_not_called()
        post.assert_called_once()

    def test_a_post_processing_failure_does_not_fail_the_move(self):
        with (
            patch.object(mover_module.shutil, 'move'),
            patch.object(mover_module, 'post_processing_songs', side_effect=RuntimeError('tagger down')),
        ):
            self.mover._move_folder('SCAN123 - Release', 'SCAN', dry_run=False)  # must not raise

    def test_a_dry_run_never_removes_a_conflicting_source_folder(self):
        with (
            patch.object(mover_module.shutil, 'move', side_effect=FileExistsError),
            patch.object(self.mover, 'remove') as remove,
        ):
            self.mover._move_folder('SCAN123 - Release', 'SCAN', dry_run=True)
        remove.assert_not_called()

    def test_a_permission_error_is_logged_and_the_source_is_kept(self):
        with (
            patch.object(mover_module.shutil, 'move', side_effect=PermissionError('read only')),
            patch.object(self.mover, 'remove') as remove,
        ):
            self.mover._move_folder('SCAN123 - Release', 'SCAN', dry_run=False)
        remove.assert_not_called()

    def test_an_unexpected_error_is_logged_and_the_source_is_kept(self):
        with (
            patch.object(mover_module.shutil, 'move', side_effect=RuntimeError('boom')),
            patch.object(self.mover, 'remove') as remove,
        ):
            self.mover._move_folder('SCAN123 - Release', 'SCAN', dry_run=False)
        remove.assert_not_called()


class RunTest(MoverTestCase):
    def test_every_folder_with_a_catalog_id_is_handed_to_the_mover(self):
        with (
            patch.object(mover_module, 'listdir', return_value=['SCAN123 - A', 'DWX456 - B']),
            patch.object(mover_module, 'isfile', return_value=False),
            patch.object(self.mover, '_move_folder') as move_folder,
        ):
            self.mover.run()
        self.assertEqual([call.args[1] for call in move_folder.call_args_list], ['SCAN', 'DWX'])

    def test_a_folder_without_a_catalog_id_is_left_for_manual_handling(self):
        with (
            patch.object(mover_module, 'listdir', return_value=['NoCatId']),
            patch.object(mover_module, 'isfile', return_value=False),
            patch.object(self.mover, '_move_folder') as move_folder,
        ):
            self.mover.run()
        move_folder.assert_not_called()

    def test_a_folder_without_a_catalog_id_is_recorded_as_a_proposal(self):
        self.mover.proposals = MagicMock()
        with (
            patch.object(mover_module, 'listdir', return_value=[' - Dewstate_-_Bass_Cannon']),
            patch.object(mover_module, 'isfile', return_value=False),
        ):
            self.mover.run()

        folder, proposal = self.mover.proposals.record.call_args.args
        self.assertEqual(folder, ' - Dewstate_-_Bass_Cannon')
        self.assertIsNone(proposal.catid)

    def test_plain_files_in_the_import_folder_are_ignored(self):
        with (
            patch.object(mover_module, 'listdir', return_value=['loose.mp3']),
            patch.object(mover_module, 'isfile', return_value=True),
            patch.object(self.mover, '_move_folder') as move_folder,
        ):
            self.mover.run()
        move_folder.assert_not_called()

    def test_the_dry_run_flag_reaches_every_folder(self):
        with (
            patch.object(mover_module, 'listdir', return_value=['SCAN123 - A']),
            patch.object(mover_module, 'isfile', return_value=False),
            patch.object(self.mover, '_move_folder') as move_folder,
        ):
            self.mover.run(dry_run=True)
        self.assertTrue(move_folder.call_args.args[2])


if __name__ == '__main__':
    unittest.main()


class MoveConflictTest(unittest.TestCase):
    """A label folder that already holds this release, against a real filesystem.

    shutil.move does not fail on an existing destination directory, it moves *into* it --
    so the bug this guards against leaves a release folder containing a folder of the same
    name, and no exception is raised anywhere. Only a real filesystem shows that.
    """

    FOLDER = 'EVAU020E - Rava_-_Vamos-(EVAU020E)-SINGLE-WEB-2026-SRG'

    def setUp(self):
        reset_database_helpers()
        self.tmp = self.enterContext(TemporaryDirectory())
        self.imports = os.path.join(self.tmp, 'import')
        self.eps = os.path.join(self.tmp, 'EPs')
        os.makedirs(os.path.join(self.eps, 'Evolve AU'))
        settings = MagicMock(import_folder_path=self.imports, eps_folder_path=self.eps, delimiter='/')
        patcher = patch.object(mover_module, 'Settings', return_value=settings)
        patcher.start()
        self.addCleanup(patcher.stop)
        double, connection = fake_connector()
        connection.cursor.return_value.__enter__.return_value.fetchone.return_value = ('Evolve AU',)
        connector = patch.object(mover_module, 'DatabaseConnector', return_value=double)
        connector.start()
        self.addCleanup(connector.stop)
        self.mover = Mover()

    def make(self, base, files):
        os.makedirs(base, exist_ok=True)
        for name, content in files.items():
            with open(os.path.join(base, name), 'w') as handle:
                handle.write(content)
        return base

    def src(self):
        return os.path.join(self.imports, self.FOLDER)

    def dst(self):
        return os.path.join(self.eps, 'Evolve AU', self.FOLDER)

    def test_a_release_the_label_folder_already_holds_is_never_nested_inside_it(self):
        self.make(self.src(), {'01-track.mp3': 'aaa'})
        self.make(self.dst(), {'01-track.mp3': 'aaa'})
        with patch.object(mover_module, 'post_processing_songs'):
            self.mover._move_folder(self.FOLDER, 'EVAU', dry_run=False)
        self.assertFalse(os.path.exists(os.path.join(self.dst(), self.FOLDER)))

    def test_the_duplicate_source_is_removed_when_both_hold_the_same_files(self):
        self.make(self.src(), {'01-track.mp3': 'aaa', '00-release.nfo': 'bb'})
        self.make(self.dst(), {'01-track.mp3': 'aaa', '00-release.nfo': 'bb'})
        with patch.object(mover_module, 'post_processing_songs'):
            self.mover._move_folder(self.FOLDER, 'EVAU', dry_run=False)
        self.assertFalse(os.path.exists(self.src()))
        self.assertTrue(os.path.exists(os.path.join(self.dst(), '01-track.mp3')))

    def test_a_different_release_under_the_same_name_is_left_alone(self):
        self.make(self.src(), {'01-track.mp3': 'a different rip'})
        self.make(self.dst(), {'01-track.mp3': 'aaa'})
        with patch.object(mover_module, 'post_processing_songs'):
            self.mover._move_folder(self.FOLDER, 'EVAU', dry_run=False)
        self.assertTrue(os.path.exists(self.src()))
        self.assertFalse(os.path.exists(os.path.join(self.dst(), self.FOLDER)))

    def test_a_conflict_is_logged_as_a_warning_saying_which_way_it_went(self):
        self.make(self.src(), {'01-track.mp3': 'a different rip'})
        self.make(self.dst(), {'01-track.mp3': 'aaa'})
        with patch.object(mover_module, 'post_processing_songs'), self.assertLogs(level='WARNING') as logs:
            self.mover._move_folder(self.FOLDER, 'EVAU', dry_run=False)
        message = '\n'.join(logs.output)
        self.assertIn('differ', message)
        self.assertIn('manual intervention', message)

    def test_a_dry_run_removes_nothing_on_a_conflict(self):
        self.make(self.src(), {'01-track.mp3': 'aaa'})
        self.make(self.dst(), {'01-track.mp3': 'aaa'})
        with patch.object(mover_module, 'post_processing_songs'):
            self.mover._move_folder(self.FOLDER, 'EVAU', dry_run=True)
        self.assertTrue(os.path.exists(self.src()))

    def test_a_release_the_label_folder_does_not_have_is_moved_as_before(self):
        self.make(self.src(), {'01-track.mp3': 'aaa'})
        with patch.object(mover_module, 'post_processing_songs') as post:
            self.mover._move_folder(self.FOLDER, 'EVAU', dry_run=False)
        self.assertFalse(os.path.exists(self.src()))
        self.assertTrue(os.path.exists(os.path.join(self.dst(), '01-track.mp3')))
        post.assert_called_once_with(self.dst())
