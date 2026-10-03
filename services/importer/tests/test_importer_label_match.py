"""Mapping a label name onto an existing label folder, on names from production."""

import os
import tempfile
import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock

from services.common.import_queue import ImportQueue
from services.importer.label_match import LabelChoice, LabelIndex, fold, load_aliases, load_choices

FOLDERS = ['B2S', 'Cloud 9 Music', 'Cloud 9 Dance', 'HARD Music', 'Hard Music Records', 'Scantraxx', 'Evolve AU']


class FoldTest(unittest.TestCase):
    def test_generic_words_case_and_punctuation_do_not_count(self):
        self.assertEqual('b2s', fold('b2s Records'))
        self.assertEqual('b2s', fold('B2S'))
        self.assertEqual('roqnrolla', fold("ROQ 'N Rolla Music"))
        self.assertEqual('dirtyandworkz', fold('Dirty & Workz'))

    def test_a_name_that_is_only_a_generic_word_keeps_it(self):
        self.assertEqual('records', fold('Records'))


class LabelIndexTest(unittest.TestCase):
    def setUp(self):
        self.index = LabelIndex(FOLDERS, {'Evolve Audio': 'Evolve AU'})

    def test_deezers_spelling_of_b2s_maps_to_the_b2s_folder(self):
        self.assertEqual('B2S', self.index.match('b2s Records'))

    def test_the_nfos_spelling_maps_too(self):
        self.assertEqual('B2S', self.index.match('B2S'))

    def test_a_name_that_folds_onto_two_folders_maps_to_none(self):
        self.assertIsNone(self.index.match('Hard Music'))

    def test_a_label_without_a_folder_maps_to_none(self):
        self.assertIsNone(self.index.match('Brutal Kuts'))
        self.assertIsNone(self.index.match(''))
        self.assertIsNone(self.index.match(None))

    def test_a_confirmed_proposal_is_an_alias(self):
        self.assertEqual('Evolve AU', self.index.match('Evolve Audio'))

    def test_the_parent_label_maps_to_the_parent_folder_not_a_sub_label(self):
        # The measured residue: the .nfo says Cloud 9 Music for a release kept under Cloud 9 Dance.
        self.assertEqual('Cloud 9 Music', self.index.match('Cloud 9 Music'))


class FromLibraryTest(unittest.TestCase):
    def test_the_import_queue_and_underscore_folders_are_never_labels(self):
        with tempfile.TemporaryDirectory() as eps:
            for name in ('B2S', '__TODO', '__Free&None', 'Scantraxx'):
                os.makedirs(os.path.join(eps, name))
            open(os.path.join(eps, 'notes.txt'), 'w', encoding='utf-8').close()

            index = LabelIndex.from_library(eps, ImportQueue(os.path.join(eps, '__TODO')), self.no_db)

        self.assertEqual({'B2S', 'Scantraxx'}, index.folders)

    def test_an_unreadable_root_is_an_empty_index(self):
        index = LabelIndex.from_library('/does/not/exist', ImportQueue('/q'), self.no_db)
        self.assertIsNone(index.match('B2S'))

    @staticmethod
    @contextmanager
    def no_db():
        raise ConnectionError('db down')
        yield  # pragma: no cover


class ChoiceTest(unittest.TestCase):
    def test_a_recorded_pair_is_found_by_any_spelling_of_the_label(self):
        pair = LabelChoice('cloud9', 'Cloud 9 Music', 'Cloud 9 Music', 'Cloud 9 Dance')
        index = LabelIndex(FOLDERS, choices=[pair])
        self.assertEqual(pair, index.choice('CLOUD 9 Music'))
        self.assertIsNone(index.choice('B2S'))

    def test_load_choices_reads_the_table_and_survives_a_missing_one(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [('cloud9', 'Cloud 9 Music', 'Cloud 9 Music', 'Cloud 9 Dance', 8, 40, None)]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        @contextmanager
        def factory():
            yield connection

        self.assertEqual(
            [LabelChoice('cloud9', 'Cloud 9 Music', 'Cloud 9 Music', 'Cloud 9 Dance', 8, 40)], load_choices(factory)
        )
        self.assertEqual([], load_choices(FromLibraryTest.no_db))


class LoadAliasesTest(unittest.TestCase):
    def test_reads_confirmed_proposals_that_changed_the_label(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [('Evolve Audio', 'Evolve AU'), ('Same', 'Same')]
        connection = MagicMock()
        connection.cursor.return_value.__enter__.return_value = cursor

        @contextmanager
        def factory():
            yield connection

        self.assertEqual({'Evolve Audio': 'Evolve AU'}, load_aliases(factory))


if __name__ == '__main__':
    unittest.main()
