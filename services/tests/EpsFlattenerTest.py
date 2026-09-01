import tempfile
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from services.other import epsflattener
from services.other.epsflattener import EpsFlattener


class EpsFlattenerTestCase(unittest.TestCase):
    """Runs against a real temporary tree: the flattener is almost entirely filesystem work."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.eps = Path(self.tmp.name)
        # Two label folders, so the EPS root itself never looks like a nested folder
        # that needs flattening -- the walk only queues folders with exactly one child.
        (self.eps / '_other_label').mkdir()
        (self.eps / '_second_label').mkdir()
        patcher = patch.object(epsflattener, 'Settings', return_value=MagicMock(eps_folder_path=str(self.eps)))
        patcher.start()
        self.addCleanup(patcher.stop)

    def make_tree(self, parent_name, sub_name, files=(), parent_files=()):
        parent = self.eps / parent_name
        subdir = parent / sub_name
        subdir.mkdir(parents=True)
        for name in files:
            (subdir / name).write_text('audio')
        for name in parent_files:
            (parent / name).write_text('audio')
        return parent, subdir


class FlattenFolderTest(EpsFlattenerTestCase):
    def test_files_are_moved_up_into_the_parent_folder(self):
        parent, subdir = self.make_tree('release', 'disc1', files=['a.mp3', 'b.mp3'])
        EpsFlattener().flatten_folder(str(parent), 'disc1')
        self.assertTrue((parent / 'a.mp3').exists())
        self.assertTrue((parent / 'b.mp3').exists())
        self.assertFalse(subdir.exists())

    def test_a_file_that_already_exists_upstairs_is_left_behind(self):
        parent, subdir = self.make_tree('release', 'disc1', files=['a.mp3'], parent_files=['a.mp3'])
        EpsFlattener().flatten_folder(str(parent), 'disc1')
        self.assertTrue((subdir / 'a.mp3').exists())

    def test_a_dry_run_moves_and_removes_nothing(self):
        parent, subdir = self.make_tree('release', 'disc1', files=['a.mp3'])
        EpsFlattener(dry_run=True).flatten_folder(str(parent), 'disc1')
        self.assertTrue((subdir / 'a.mp3').exists())
        self.assertFalse((parent / 'a.mp3').exists())

    def test_a_subfolder_repeating_its_parent_name_is_force_removed(self):
        parent, subdir = self.make_tree('release', 'release', files=['a.mp3', 'a.mp3'])
        (subdir / 'leftover.cue').write_text('x')
        (parent / 'leftover.cue').write_text('x')
        EpsFlattener().flatten_folder(str(parent), 'release')
        self.assertFalse(subdir.exists())

    def test_a_subfolder_that_still_holds_files_is_kept(self):
        parent, subdir = self.make_tree('release', 'disc1', files=['a.mp3'], parent_files=['a.mp3'])
        EpsFlattener().flatten_folder(str(parent), 'disc1')
        self.assertTrue(subdir.exists())

    def test_a_path_that_is_not_a_directory_is_ignored(self):
        parent = self.eps / 'release'
        parent.mkdir()
        (parent / 'notafolder').write_text('x')
        EpsFlattener().flatten_folder(str(parent), 'notafolder')
        self.assertTrue((parent / 'notafolder').is_file())

    def test_a_failure_halfway_through_is_logged_rather_than_raised(self):
        parent, _ = self.make_tree('release', 'disc1', files=['a.mp3'])
        with (
            patch.object(epsflattener.shutil, 'move', side_effect=PermissionError('read only')),
            self.assertLogs(level='ERROR'),
        ):
            EpsFlattener().flatten_folder(str(parent), 'disc1')  # must not raise


class RunTest(EpsFlattenerTestCase):
    def test_a_folder_with_exactly_one_subfolder_is_flattened(self):
        parent, subdir = self.make_tree('release', 'disc1', files=['a.mp3'])
        EpsFlattener().run()
        self.assertTrue((parent / 'a.mp3').exists())

    def test_a_folder_with_several_subfolders_is_left_alone(self):
        parent = self.eps / 'label'
        (parent / 'a').mkdir(parents=True)
        (parent / 'b').mkdir()
        (parent / 'a' / 'x.mp3').write_text('audio')
        EpsFlattener().run()
        self.assertTrue((parent / 'a' / 'x.mp3').exists())

    def test_synology_metadata_folders_do_not_count_as_a_subfolder(self):
        parent, subdir = self.make_tree('release', 'disc1', files=['a.mp3'])
        (parent / '@eaDir').mkdir()
        EpsFlattener().run()
        self.assertTrue((parent / 'a.mp3').exists())

    def test_a_tree_with_nothing_to_flatten_finishes_quietly(self):
        (self.eps / 'label' / 'a').mkdir(parents=True)
        (self.eps / 'label' / 'b').mkdir()
        with self.assertLogs(level='INFO') as logs:
            EpsFlattener().run()
        self.assertTrue(any('No nested folders' in line for line in logs.output))


if __name__ == '__main__':
    unittest.main()
