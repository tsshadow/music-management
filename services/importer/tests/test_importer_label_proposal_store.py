import unittest
from unittest.mock import MagicMock, patch

from services.importer import label_proposal_store
from services.importer.label_proposal_store import NEW_ROW, KnownProposal, LabelProposalStore, fingerprint
from services.importer.label_resolver import LabelProposal


class LabelProposalStoreTest(unittest.TestCase):
    """
    The importer meets the same unplaceable folder on every cycle, so the store has to
    be able to write the same row over and over without undoing a decision a human
    already made about it.
    """

    def setUp(self):
        self.cursor = MagicMock()
        self.connection = MagicMock()
        self.connection.cursor.return_value.__enter__.return_value = self.cursor
        connector = MagicMock()
        connector.connection.return_value.__enter__.return_value = self.connection
        patcher = patch.object(label_proposal_store, 'DatabaseConnector', return_value=connector)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.store = LabelProposalStore()

    def test_a_proposal_is_written_with_its_folder_as_the_key(self):
        self.store.record('BKRP104 - Darwin', LabelProposal('Brutal Kuts', 'tag:label', 90, 'BKRP'))

        query, params = self.cursor.execute.call_args.args
        self.assertIn('rules_label_proposals', query)
        self.assertEqual(params, ('BKRP104 - Darwin', 'BKRP', 'Brutal Kuts', 'tag:label', 90, None, None, None))

    def test_the_write_is_committed(self):
        self.store.record('BKRP104 - Darwin', LabelProposal('Brutal Kuts', 'tag:label', 90, 'BKRP'))

        self.connection.commit.assert_called_once()

    def test_a_decided_row_is_not_reopened_by_a_later_scan(self):
        self.store.record('BKRP104 - Darwin', LabelProposal('Brutal Kuts', 'tag:label', 90, 'BKRP'))

        query, _ = self.cursor.execute.call_args.args
        self.assertIn('ON DUPLICATE KEY UPDATE', query)
        self.assertIn("status = 'new'", query)

    def test_a_release_without_any_proposal_is_still_recorded(self):
        self.store.record(' - Dewstate_-_Bass_Cannon', LabelProposal(None, 'none', 0, None))

        _, params = self.cursor.execute.call_args.args
        self.assertEqual(params, (' - Dewstate_-_Bass_Cannon', None, None, 'none', 0, None, None, None))

    def test_the_fingerprint_is_written_even_on_a_decided_row(self):
        self.store.record('BKRP104 - Darwin', LabelProposal('Brutal Kuts', 'tag:label', 90, 'BKRP'), 'f' * 64)

        query, params = self.cursor.execute.call_args.args
        self.assertEqual(params[5], 'f' * 64)
        self.assertIn('resolved_fingerprint = VALUES(resolved_fingerprint)', query)

    def test_the_snapshot_reads_the_rules_version_and_every_row(self):
        self.cursor.fetchone.return_value = (3, 987654)
        self.cursor.fetchall.return_value = [
            ('A - One', 'new', None, 'abc', 'first'),
            ('B - Two', 'rejected', 'then', None, None),
        ]

        snapshot = self.store.snapshot()

        self.assertEqual(snapshot.rules_version, '3:987654')
        self.assertEqual(snapshot.rows['A - One'], KnownProposal('new', None, 'abc', 'first'))
        self.assertEqual(snapshot.rows['B - Two'].status, 'rejected')
        first_query = self.cursor.execute.call_args_list[0].args[0]
        self.assertIn('rules_catid_label', first_query)

    def test_an_unreadable_snapshot_is_none(self):
        self.cursor.execute.side_effect = RuntimeError('gone')

        self.assertIsNone(self.store.snapshot())

    def test_the_fingerprint_changes_with_each_of_its_inputs(self):
        base = fingerprint('2:10:1.0', '3:99', NEW_ROW)

        self.assertEqual(base, fingerprint('2:10:1.0', '3:99', KnownProposal('new', None, 'ignored')))
        self.assertNotEqual(base, fingerprint('2:10:2.0', '3:99', NEW_ROW))
        self.assertNotEqual(base, fingerprint('2:10:1.0', '4:99', NEW_ROW))
        self.assertNotEqual(base, fingerprint('2:10:1.0', '3:99', KnownProposal('rejected', 'then', None)))

    def test_a_database_failure_does_not_raise(self):
        self.cursor.execute.side_effect = RuntimeError('gone')

        self.store.record('X', LabelProposal(None, 'none', 0, None))


if __name__ == '__main__':
    unittest.main()
