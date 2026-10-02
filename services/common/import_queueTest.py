"""Where the import queue is, and what walkers of the label tree may call a label (bug report 087)."""

import unittest
from unittest.mock import MagicMock

from services.common.import_queue import LEGACY_QUEUE_NAME, ImportQueue
from services.common.label_namesTest import REAL_LABELS, RELEASE_FOLDER_LABELS


class FromSettingsTest(unittest.TestCase):
    def test_the_configured_path_wins(self):
        settings = MagicMock(import_folder_path='/mnt/music/import/', eps_folder_path='/mnt/music/EPs')
        self.assertEqual('/mnt/music/import', ImportQueue.from_settings(settings).path)

    def test_unset_falls_back_to_where_it_always_was(self):
        # Default unchanged: <eps root>/__TODO.
        settings = MagicMock(import_folder_path='', eps_folder_path='/mnt/music/EPs')
        self.assertEqual('/mnt/music/EPs/' + LEGACY_QUEUE_NAME, ImportQueue.from_settings(settings).path)

    def test_a_mock_attribute_is_not_a_path(self):
        # Half the suite hands in a bare MagicMock; its attributes must read as unset.
        settings = MagicMock(eps_folder_path='/eps')
        self.assertEqual('/eps/' + LEGACY_QUEUE_NAME, ImportQueue.from_settings(settings).path)

    def test_nothing_configured_is_no_queue(self):
        queue = ImportQueue.from_settings(MagicMock(import_folder_path='', eps_folder_path=''))
        self.assertEqual('', queue.path)
        self.assertFalse(queue.contains('/anything'))


class ContainsTest(unittest.TestCase):
    queue = ImportQueue('/mnt/music/EPs/__TODO')

    def test_the_queue_and_everything_below_it(self):
        self.assertTrue(self.queue.contains('/mnt/music/EPs/__TODO'))
        self.assertTrue(self.queue.contains('/mnt/music/EPs/__TODO/Release/track.mp3'))

    def test_a_sibling_sharing_the_prefix_is_not_in_it(self):
        self.assertFalse(self.queue.contains('/mnt/music/EPs/__TODO_old/Release/track.mp3'))
        self.assertFalse(self.queue.contains('/mnt/music/EPs/Label/Release/track.mp3'))

    def test_lies_within(self):
        self.assertTrue(self.queue.lies_within('/mnt/music/EPs/'))
        self.assertFalse(ImportQueue('/mnt/music/import').lies_within('/mnt/music/EPs'))


class IsLabelFolderTest(unittest.TestCase):
    def test_the_queue_is_no_label_whatever_it_is_called(self):
        queue = ImportQueue('/mnt/music/EPs/Intake')
        self.assertFalse(queue.is_label_folder('/mnt/music/EPs/Intake'))

    def test_an_underscore_folder_is_no_label(self):
        self.assertFalse(ImportQueue('/q').is_label_folder('/mnt/music/EPs/__Free&None'))

    def test_an_ordinary_folder_is_a_label(self):
        self.assertTrue(ImportQueue('/mnt/music/EPs/__TODO').is_label_folder('/mnt/music/EPs/Scantraxx'))


class PlaceholderTest(unittest.TestCase):
    def test_the_legacy_name_stays_a_placeholder_after_a_move(self):
        queue = ImportQueue('/mnt/music/import')
        self.assertTrue(queue.is_placeholder_publisher('__TODO'))
        self.assertTrue(queue.is_placeholder_publisher(' __todo '))
        self.assertTrue(queue.is_placeholder_publisher('import'))
        self.assertFalse(queue.is_placeholder_publisher('Scantraxx'))
        self.assertFalse(queue.is_placeholder_publisher(''))

    def test_a_copyright_computed_from_the_placeholder(self):
        queue = ImportQueue('/mnt/music/EPs/__TODO')
        self.assertTrue(queue.is_placeholder_copyright('__TODO (2021)'))
        self.assertTrue(queue.is_placeholder_copyright('__TODO'))
        self.assertFalse(queue.is_placeholder_copyright('Scantraxx (2021)'))
        self.assertFalse(queue.is_placeholder_copyright(None))


class FolderNamePlaceholderTest(unittest.TestCase):
    """Bug report 146: underscore folders and release folders are no publisher either."""

    queue = ImportQueue('/mnt/music/EPs/__TODO')

    def test_underscore_folder_names_are_placeholders(self):
        for value in ('__Free&None', '___Free&None', ' __free&none '):
            with self.subTest(value=value):
                self.assertTrue(self.queue.is_placeholder_publisher(value))

    def test_a_release_folder_name_is_a_placeholder(self):
        for value in RELEASE_FOLDER_LABELS:
            with self.subTest(value=value):
                self.assertTrue(self.queue.is_placeholder_publisher(value))

    def test_real_labels_are_not(self):
        for value in REAL_LABELS:
            with self.subTest(value=value):
                self.assertFalse(self.queue.is_placeholder_publisher(value))

    def test_copyrights_computed_from_them(self):
        self.assertTrue(self.queue.is_placeholder_copyright('__Free&None (2020)'))
        self.assertTrue(self.queue.is_placeholder_copyright(RELEASE_FOLDER_LABELS[0] + ' (2026)'))
        self.assertFalse(self.queue.is_placeholder_copyright('DWX Copyright Free (2024)'))


if __name__ == '__main__':
    unittest.main()
