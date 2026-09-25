"""The rename planner for import folders with an empty catalogue-number prefix (bug report 087)."""

import json
import os
import tempfile
import unittest
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.mock_base('Cache')

from services.importer.catid_prefix_repair import (  # noqa: E402
    Proposal,
    apply_plan,
    is_crooked,
    name_candidates,
    plan,
    plan_one,
    rollback,
    summarize,
)

RULES = {'scan': 'Scantraxx', 'dwx': 'Dirty Workz', 'rrbm': 'Le Diable Au Corps'}
CROOKED = ' - Artist_-_Title-WEB-FLAC-2025'


class PlanOneTest(unittest.TestCase):
    def test_a_proposal_catid_a_rule_knows_is_used(self):
        entry = plan_one(CROOKED, Proposal('SCAN123', 'Scantraxx', None), RULES)

        self.assertEqual('SCAN123 - Artist_-_Title-WEB-FLAC-2025', entry.new)
        self.assertEqual(('proposal', 'Scantraxx'), (entry.source, entry.label))

    def test_a_upc_or_junk_catid_routes_nowhere(self):
        # What most proposal catids on production are: UPCs, distributor ids and 'none'.
        for catid in ('199934842531', 'none', 'CAT1424691', ''):
            with self.subTest(catid=catid):
                entry = plan_one(CROOKED, Proposal(catid, 'Magistrates Music', None), RULES)
                self.assertIsNone(entry.new)
                self.assertEqual('no catalogue number a rule knows', entry.reason)

    def test_a_catalogue_number_in_the_name_is_found(self):
        entry = plan_one(' - Artist_-_Title-DWX123-WEB-2025', None, RULES)

        self.assertEqual('DWX123 - Artist_-_Title-DWX123-WEB-2025', entry.new)
        self.assertEqual('name', entry.source)

    def test_a_parenthesised_group_without_digits_is_found(self):
        # find_cat_id only takes groups with a digit; (RRBM) is what it left behind.
        entry = plan_one(' - Nout_Heretik_-_Rage-(RRBM)-WEB-FLAC-2026', None, RULES)

        self.assertEqual('RRBM', entry.catid)

    def test_two_rules_in_one_name_are_ambiguous(self):
        entry = plan_one(' - A_-_B-DWX123-SCAN456-WEB', None, RULES)

        self.assertIsNone(entry.new)
        self.assertTrue(entry.reason.startswith('ambiguous'))

    def test_a_decided_label_that_disagrees_wins_over_the_rule(self):
        entry = plan_one(CROOKED, Proposal('SCAN123', None, 'Dirty Workz'), RULES)

        self.assertIsNone(entry.new)
        self.assertIn('decided label is Dirty Workz', entry.reason)

    def test_spaces_inside_a_catid_are_dropped(self):
        entry = plan_one(CROOKED, Proposal('SCAN 123', None, None), RULES)

        self.assertTrue(entry.new.startswith('SCAN123 - '))

    def test_name_candidates_skip_plain_words_and_years(self):
        self.assertEqual(['DWX123'], name_candidates('Artist_-_Title-DWX123-WEB-FLAC-2025'))


class PlanTest(unittest.TestCase):
    def test_only_crooked_folders_are_planned(self):
        planned = plan(['SCAN1 - ok', CROOKED], {CROOKED: Proposal('SCAN999', None, None)}, RULES)

        self.assertEqual([CROOKED], [entry.old for entry in planned])
        self.assertTrue(is_crooked(CROOKED))
        self.assertFalse(is_crooked('SCAN1 - ok'))

    def test_a_rename_onto_an_existing_folder_is_refused(self):
        taken = 'SCAN999 - Artist_-_Title-WEB-FLAC-2025'
        planned = plan([CROOKED, taken], {CROOKED: Proposal('SCAN999', None, None)}, RULES)

        self.assertIsNone(planned[0].new)
        self.assertTrue(planned[0].reason.startswith('target exists'))

    def test_summary_counts(self):
        planned = plan(
            [CROOKED, ' - Other-WEB'],
            {CROOKED: Proposal('SCAN999', None, None)},
            RULES,
        )
        summary = summarize(planned)

        self.assertEqual((2, 1), (summary['crooked'], summary['renameable']))
        self.assertEqual({'Scantraxx': 1}, summary['by_label'])
        self.assertEqual({'no catalogue number a rule knows': 1}, summary['undecidable'])


class ApplyAndRollbackTest(unittest.TestCase):
    def setUp(self):
        self.tmp = self.enterContext(tempfile.TemporaryDirectory())  # pylint: disable=consider-using-with
        self.queue = os.path.join(self.tmp, 'queue')
        os.makedirs(os.path.join(self.queue, CROOKED))
        self.log = os.path.join(self.tmp, 'renames.jsonl')
        self.connection = MagicMock()

    def test_apply_renames_logs_and_moves_the_proposal_then_rollback_restores(self):
        planned = plan(os.listdir(self.queue), {CROOKED: Proposal('SCAN999', None, None)}, RULES)

        result = apply_plan(planned, self.queue, self.log, self.connection)

        new = 'SCAN999 - Artist_-_Title-WEB-FLAC-2025'
        self.assertEqual(1, result['renamed'])
        self.assertEqual([new], os.listdir(self.queue))
        with open(self.log, encoding='utf-8') as handle:
            self.assertEqual(
                {'old': CROOKED, 'new': new}, {k: v for k, v in json.loads(handle.read()).items() if k != 'at'}
            )
        cursor = self.connection.cursor.return_value.__enter__.return_value
        self.assertEqual((new, CROOKED, new), cursor.execute.call_args.args[1])

        undone = rollback(self.log, self.queue, self.connection)

        self.assertEqual(1, undone['restored'])
        self.assertEqual([CROOKED], os.listdir(self.queue))

    def test_rollback_reports_a_release_the_mover_already_placed(self):
        with open(self.log, 'w', encoding='utf-8') as handle:
            handle.write(json.dumps({'old': 'gone-old', 'new': 'gone-new'}) + '\n')

        undone = rollback(self.log, self.queue, self.connection)

        self.assertEqual(['gone-new'], undone['no_longer_in_queue'])


if __name__ == '__main__':
    unittest.main()
