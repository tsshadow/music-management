"""The repair of import folders the old Renamer misnamed (bug report 145), on production names."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.mock_base('Cache')

from services.importer.catid_prefix_repair import Proposal, apply_plan, rollback  # noqa: E402
from services.importer.prefix_strip_repair import crooked_rest, plan, plan_one, summarize  # noqa: E402

MINUS_MILITIA = (
    'Minus_Militia_And_Nolz_-_Recover_The_Archive_(Official_Hardbass_2026_Anthem)_(Edit)-SINGLE-WEB-2026-UTNG'
)
WORD_PREFIXED = 'Official_Hardbass_2026_Anthem - ' + MINUS_MILITIA
EMPTY_PREFIXED = ' - Guizcore_-_Coffee_Time-WEB-FLAC-2026'
RULES = {'scan': 'Scantraxx'}


class CrookedRestTest(unittest.TestCase):
    def test_an_empty_prefix_in_both_spellings(self):
        self.assertEqual(('empty', 'Guizcore_-_Coffee_Time-WEB-FLAC-2026'), crooked_rest(EMPTY_PREFIXED))
        self.assertEqual(('empty', 'Amigo_-_Uptempo_Fiesta_Vol.1-WEB-2026'), crooked_rest('- Amigo_-_Uptempo_Fiesta_Vol.1-WEB-2026'))

    def test_a_festival_anthem_prefix(self):
        self.assertEqual(('word', MINUS_MILITIA), crooked_rest(WORD_PREFIXED))

    def test_a_real_catalogue_number_prefix_is_left_alone(self):
        self.assertIsNone(crooked_rest('HA037 - Hexus_-_The_Mission-(HA037)-WEB-2026'))

    def test_a_prefix_a_person_typed_is_left_alone(self):
        # HZH has no digit, so the old Renamer cannot have produced it.
        self.assertIsNone(crooked_rest('HZH - VA_-_Hardcore_Zonder_Hokjes_(HZH)-WEB-2023'))

    def test_a_word_prefix_that_is_not_the_old_rules_pick_is_left_alone(self):
        self.assertIsNone(crooked_rest('Official_2024_Anthem - Some_Other_Name-WEB-2024'))


class PlanTest(unittest.TestCase):
    def test_the_minus_militia_folder_gets_its_name_back(self):
        entry = plan_one(WORD_PREFIXED, None, RULES)

        self.assertEqual(MINUS_MILITIA, entry.new)
        self.assertEqual('strip', entry.source)

    def test_a_one_prefix_becomes_the_real_catalogue_number(self):
        name = '1 - DKR_-_Music_Is_Life_E.P.-(ESU054)-WEB-2026 (1)'

        entry = plan_one(name, None, RULES)

        self.assertEqual('ESU054 - DKR_-_Music_Is_Life_E.P.-(ESU054)-WEB-2026 (1)', entry.new)
        self.assertEqual('name', entry.source)

    def test_an_empty_prefix_with_a_routed_proposal_catid_gets_that_number(self):
        entry = plan_one(EMPTY_PREFIXED, Proposal('SCAN999', None, None), RULES)

        self.assertEqual('SCAN999 - Guizcore_-_Coffee_Time-WEB-FLAC-2026', entry.new)
        self.assertEqual(EMPTY_PREFIXED, entry.old)
        self.assertEqual('proposal', entry.source)

    def test_an_empty_prefix_without_one_is_stripped(self):
        entry = plan_one(EMPTY_PREFIXED, None, RULES)

        self.assertEqual('Guizcore_-_Coffee_Time-WEB-FLAC-2026', entry.new)

    def test_a_rename_onto_a_name_already_in_the_queue_is_refused(self):
        planned = plan([EMPTY_PREFIXED, 'Guizcore_-_Coffee_Time-WEB-FLAC-2026'], {}, RULES)

        self.assertEqual(1, len(planned))
        self.assertIsNone(planned[0].new)
        self.assertTrue(planned[0].reason.startswith('target exists'))

    def test_two_folders_that_would_end_up_the_same_are_not_both_renamed(self):
        planned = plan([' - X-WEB-2026', '- X-WEB-2026'], {}, RULES)

        self.assertEqual(1, sum(1 for entry in planned if entry.new))

    def test_other_folders_are_not_planned(self):
        self.assertEqual([], plan(['HA037 - Hexus-(HA037)-WEB-2026', 'Collusion_-_PSYKO-(TCRECPRO173)-WEB-2026'], {}, RULES))

    def test_summary(self):
        planned = plan([EMPTY_PREFIXED, WORD_PREFIXED, 'Guizcore_-_Coffee_Time-WEB-FLAC-2026'], {}, RULES)

        summary = summarize(planned)

        self.assertEqual(2, summary['misnamed'])
        self.assertEqual(1, summary['empty_prefix'])
        self.assertEqual(1, summary['word_prefix'])
        self.assertEqual(1, summary['renameable'])
        self.assertEqual({'target exists': 1}, summary['refused'])


class ApplyTest(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())  # pylint: disable=consider-using-with
        self.queue = os.path.join(self.tmp, 'queue')
        os.makedirs(os.path.join(self.queue, WORD_PREFIXED))
        self.log = os.path.join(self.tmp, 'renames.jsonl')
        self.connection = MagicMock()

    def test_apply_is_logged_moves_the_proposal_row_and_rolls_back(self):
        notified = []
        planned = plan(os.listdir(self.queue), {}, RULES)

        result = apply_plan(planned, self.queue, self.log, self.connection, notify=notified.append)

        self.assertEqual(1, result['renamed'])
        self.assertEqual([MINUS_MILITIA], os.listdir(self.queue))
        with open(self.log, encoding='utf-8') as handle:
            self.assertEqual(MINUS_MILITIA, json.loads(handle.read())['new'])
        self.assertEqual(1, len(notified))
        cursor = self.connection.cursor.return_value.__enter__.return_value
        self.assertEqual((MINUS_MILITIA, WORD_PREFIXED, MINUS_MILITIA), cursor.execute.call_args.args[1])

        undone = rollback(self.log, self.queue, self.connection)

        self.assertEqual(1, undone['restored'])
        self.assertEqual([WORD_PREFIXED], os.listdir(self.queue))

    def test_a_second_apply_finds_nothing_left_to_do(self):
        apply_plan(plan(os.listdir(self.queue), {}, RULES), self.queue, self.log, self.connection)

        self.assertEqual([], plan(os.listdir(self.queue), {}, RULES))


if __name__ == '__main__':
    unittest.main()
