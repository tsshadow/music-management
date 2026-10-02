"""Learning name-versus-filing pairs from the label tree (#164), on production label names."""

import os
import tempfile
import unittest
from unittest.mock import MagicMock

from services.common.import_queue import ImportQueue
from services.common.release_nfo import NfoInfo
from services.importer.label_history import Pair, learn, store, walk_label_tree
from services.importer.label_match import LabelIndex

INDEX = LabelIndex(['Cloud 9 Music', 'Cloud 9 Dance', 'B2S', 'Brandstichters'])


class LearnTest(unittest.TestCase):
    def test_a_label_filed_elsewhere_becomes_a_pair_with_counts_and_examples(self):
        releases = [
            ('Cloud 9 Dance', 'CLDM2019000 - VA_-_Snakepit_2019', 'Cloud 9 Music'),
            ('Cloud 9 Dance', 'CLDG2017166 - VA_-_Snakepit', 'Cloud 9 Music'),
            ('Cloud 9 Dance', 'CLDG2017167 - VA_-_Third', 'Cloud 9 Music'),
            ('Cloud 9 Music', 'CLDM001 - Fine', 'Cloud 9 Music'),
            ('B2S', 'BS220035 - Ransom', 'Brandstichters'),
            ('B2S', 'B2S001 - Minus_Militia', 'B2S'),
            ('B2S', 'B2S002 - No_nfo', None),
            ('B2S', 'B2S003 - Unknown_label', 'Henergy Records'),
        ]

        pairs = learn(releases, INDEX)

        self.assertEqual(
            [
                Pair(
                    'cloud9',
                    'Cloud 9 Music',
                    'Cloud 9 Music',
                    'Cloud 9 Dance',
                    3,
                    1,
                    ['CLDM2019000 - VA_-_Snakepit_2019', 'CLDG2017166 - VA_-_Snakepit'],
                ),
                Pair('brandstichters', 'Brandstichters', 'Brandstichters', 'B2S', 1, 0, ['BS220035 - Ransom']),
            ],
            pairs,
        )

    def test_agreement_alone_is_no_pair(self):
        self.assertEqual([], learn([('B2S', 'B2S001 - X', 'b2s Records')], INDEX))


class WalkTest(unittest.TestCase):
    def test_walks_label_folders_only(self):
        with tempfile.TemporaryDirectory() as eps:
            for path in ('B2S/B2S001 - X', '__TODO/ - Y', '__Free&None/Z'):
                os.makedirs(os.path.join(eps, path))
            found = list(
                walk_label_tree(eps, ImportQueue(os.path.join(eps, '__TODO')), read=lambda p: NfoInfo(label='B2S'))
            )
        self.assertEqual([('B2S', 'B2S001 - X', 'B2S')], found)


class StoreTest(unittest.TestCase):
    def test_upserts_without_touching_the_choice(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value

        store(connection, [Pair('cloud9', 'Cloud 9 Music', 'Cloud 9 Music', 'Cloud 9 Dance', 3, 1, ['a', 'b'])])

        sql, params = cursor.execute.call_args.args
        self.assertNotIn('chosen_folder', sql)
        self.assertEqual(('cloud9', 'Cloud 9 Music', 'Cloud 9 Music', 'Cloud 9 Dance', 3, 1, 'a | b'), params)
        connection.commit.assert_called_once()


if __name__ == '__main__':
    unittest.main()
