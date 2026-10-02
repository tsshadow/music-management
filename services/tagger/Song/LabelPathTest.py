"""Which folder in a path is the label, and when the path names none (bug reports 030 and 146)."""

import unittest

from services.common.import_queue import ImportQueue
from services.common.label_namesTest import REAL_LABELS
from services.tagger.Song import LabelPath

EPS = '/mnt/music/EPs'
QUEUE = ImportQueue(EPS + '/__TODO')
RELEASE = 'STH685RMXBP - Bassjackers_-_I_Fink_U_Freeky_(Coone_Remix)-(STH685RMXBP)-SINGLE-WEB-2026-SRG'
INNER = 'Bassjackers_-_I_Fink_U_Freeky_(Coone_Remix)-(STH685RMXBP)-SINGLE-WEB-2026-SRG'


def split(path, root=EPS, queue=QUEUE):
    return LabelPath.split(path, root, '/', queue)


class InsideTheRootTest(unittest.TestCase):
    def test_label_and_release_come_from_the_first_two_folders(self):
        self.assertEqual(('Spinnin', RELEASE), split(f'{EPS}/Spinnin/{RELEASE}/01.mp3'))

    def test_a_copy_of_the_release_inside_itself_keeps_the_label(self):
        # The nested scene copy that used to make the release folder the label (0.24.0).
        self.assertEqual(('Spinnin', RELEASE), split(f'{EPS}/Spinnin/{RELEASE}/{INNER}/01.mp3'))

    def test_a_track_loose_in_a_label_folder_still_has_its_label(self):
        self.assertEqual(('Fusion Records', ''), split(f'{EPS}/Fusion Records/01.mp3'))

    def test_real_labels_stay_labels(self):
        for label in REAL_LABELS:
            with self.subTest(label=label):
                self.assertEqual((label, RELEASE), split(f'{EPS}/{label}/{RELEASE}/01.mp3'))

    def test_an_underscore_folder_names_no_label(self):
        for folder in ('__Free&None', '___Free&None'):
            with self.subTest(folder=folder):
                self.assertEqual(
                    ('', ''), split(f'{EPS}/{folder}/FREE - Pat_B_-_USB_Album_3.0-FLASH-EXTRAS-2023-SOB/13.mp3')
                )
                self.assertEqual(('', ''), split(f'{EPS}/{folder}/{RELEASE}/{INNER}/01.mp3'))

    def test_the_import_queue_names_no_label_whatever_it_is_called(self):
        self.assertEqual(('', ''), split(f'{EPS}/__TODO/{RELEASE}/01.mp3'))
        self.assertEqual(('', ''), split(f'{EPS}/Intake/{RELEASE}/01.mp3', queue=ImportQueue(EPS + '/Intake')))

    def test_without_a_queue_the_names_are_still_judged(self):
        self.assertEqual(('', ''), split(f'{EPS}/__Free&None/{RELEASE}/01.mp3', queue=None))

    def test_a_release_directly_in_the_root_is_not_its_own_label(self):
        # Its folder still names the release, so the catalogue number survives.
        self.assertEqual(('', RELEASE), split(f'{EPS}/{RELEASE}/01.mp3'))
        self.assertEqual(('', RELEASE), split(f'{EPS}/{RELEASE}/{INNER}/01.mp3'))

    def test_a_file_in_the_root_has_nothing(self):
        self.assertEqual(('', ''), split(f'{EPS}/01.mp3'))


class OutsideTheRootTest(unittest.TestCase):
    def test_the_two_folders_above_the_file(self):
        self.assertEqual(('Spinnin', RELEASE), split(f'/import/Spinnin/{RELEASE}/01.mp3'))

    def test_a_nested_copy_does_not_make_the_release_the_label(self):
        # Counting parents lands on the outer release folder; that is no label.
        self.assertEqual(('', ''), split(f'/import/{RELEASE}/{INNER}/01.mp3'))

    def test_the_queue_and_underscore_folders_name_no_label(self):
        self.assertEqual(('', ''), split(f'/import/__Free&None/{RELEASE}/01.mp3', root=''))
        self.assertEqual(('', ''), split(f'{EPS}/__TODO/{RELEASE}/01.mp3', root=''))

    def test_too_short_a_path(self):
        self.assertEqual(('', ''), split('01.mp3', root=''))


class CatalogNumberTest(unittest.TestCase):
    def test_first_word_of_the_release_folder(self):
        self.assertEqual('STH685RMXBP', LabelPath.catalog_number(RELEASE))
        self.assertEqual('', LabelPath.catalog_number(''))


if __name__ == '__main__':
    unittest.main()
