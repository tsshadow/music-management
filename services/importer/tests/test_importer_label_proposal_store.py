import unittest
from unittest.mock import MagicMock, patch

from services.importer import label_proposal_store
from services.importer.label_proposal_store import LabelProposalStore
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
        self.assertEqual(params, ('BKRP104 - Darwin', 'BKRP', 'Brutal Kuts', 'tag:label', 90))

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
        self.assertEqual(params, (' - Dewstate_-_Bass_Cannon', None, None, 'none', 0))

    def test_a_database_failure_does_not_raise(self):
        self.cursor.execute.side_effect = RuntimeError('gone')

        self.store.record('X', LabelProposal(None, 'none', 0, None))


if __name__ == '__main__':
    unittest.main()
