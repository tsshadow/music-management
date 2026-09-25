"""What the mover repeats on every cycle, and what it tells the phone.

Two costs that grew with the import folder: every unplaceable folder had its tags read
again over CIFS on every cycle (~2.266 folders every 300 s on production), and every
imported *file* was a phone push -- a 44-release pack was well over a hundred of them.
"""

import os
import time
import unittest
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import pytest

from services.tests.connector_fakes import fake_connector
from services.tests.mock_base import reset_database_helpers

pytestmark = pytest.mark.mock_base('Cache')

from services.importer import mover as mover_module  # noqa: E402
from services.importer import settle  # noqa: E402
from services.importer.label_proposal_store import KnownProposal, ProposalSnapshot  # noqa: E402
from services.importer.label_resolver import LabelProposal  # noqa: E402
from services.importer.mover import Mover, release_summary  # noqa: E402

AN_HOUR_AGO = time.time() - 3600


class FakeProposalStore:
    """`rules_label_proposals` and `rules_catid_label` as far as the mover sees them.

    Outlives a Mover, the way the database outlives the importer process.
    """

    def __init__(self):
        self.rules_version = '0:0'
        self.rows: dict[str, KnownProposal] = {}
        self.record = MagicMock(side_effect=self._record)
        self.unreachable = False

    def _record(self, folder, proposal, resolved_fingerprint=None):
        row = self.rows.get(folder, KnownProposal('new', None, None))
        self.rows[folder] = KnownProposal(row.status, row.decided_at, resolved_fingerprint)

    def snapshot(self):
        if self.unreachable:
            return None
        return ProposalSnapshot(self.rules_version, dict(self.rows))

    def decide(self, folder, status, decided_at):
        row = self.rows[folder]
        self.rows[folder] = KnownProposal(status, decided_at, row.fingerprint)


class MoverOnDiskTest(unittest.TestCase):
    """A mover over a real import folder, with the database and the tagger replaced."""

    def setUp(self):
        reset_database_helpers()
        self.root = self.enterContext(TemporaryDirectory())
        self.imports = os.path.join(self.root, 'import')
        self.eps = os.path.join(self.root, 'EPs')
        os.makedirs(os.path.join(self.eps, 'Scantraxx'))
        settings = MagicMock(import_folder_path=self.imports, eps_folder_path=self.eps, delimiter='/')
        self.enterContext(patch.object(mover_module, 'Settings', return_value=settings))
        connector, _ = fake_connector()
        self.enterContext(patch.object(mover_module, 'DatabaseConnector', return_value=connector))
        self.enterContext(patch.object(settle, 'settle_seconds', return_value=0))
        self.resolve = self.enterContext(
            patch.object(mover_module, 'resolve', return_value=LabelProposal(None, 'none', 0, None))
        )
        self.notify = self.enterContext(patch.object(mover_module, 'notification_service')).notify
        self.store = FakeProposalStore()
        self.mover = self.new_mover()

    def new_mover(self):
        mover = Mover()
        mover.proposals = self.store
        mover.get_label = MagicMock(return_value=None)
        return mover

    def release(self, folder, tracks=('01.mp3',)):
        path = os.path.join(self.imports, folder)
        os.makedirs(path)
        for name in tracks:
            with open(os.path.join(path, name), 'w', encoding='utf-8') as handle:
                handle.write('audio')
            os.utime(os.path.join(path, name), (AN_HOUR_AGO, AN_HOUR_AGO))
        os.utime(path, (AN_HOUR_AGO, AN_HOUR_AGO))
        return path


class ProposalIsNotResolvedEveryCycleTest(MoverOnDiskTest):
    def test_an_unchanged_unplaceable_folder_is_resolved_once(self):
        self.release('UNKNOWN123 - Release')

        for _ in range(3):
            self.mover.run()

        self.assertEqual(self.resolve.call_count, 1)
        self.assertEqual(self.mover.proposals.record.call_count, 1)

    def test_a_folder_without_a_catalog_number_is_resolved_once_too(self):
        self.release('NoCatalogNumber')

        self.mover.run()
        self.mover.run()

        self.assertEqual(self.resolve.call_count, 1)

    def test_a_folder_that_changed_is_resolved_again(self):
        path = self.release('UNKNOWN123 - Release')
        self.mover.run()

        with open(os.path.join(path, '02.mp3'), 'w', encoding='utf-8') as handle:
            handle.write('a track that arrived later')
        self.mover.run()

        self.assertEqual(self.resolve.call_count, 2)

    def test_a_decided_proposal_still_moves_the_folder(self):
        """Confirming a proposal adds the catalogue rule; the lookup comes before the cache."""
        self.release('UNKNOWN123 - Release')
        self.mover.run()

        self.mover.get_label.return_value = 'Scantraxx'
        with patch.object(mover_module, 'post_processing_songs', return_value=1):
            self.mover.run()

        self.assertTrue(os.path.isdir(os.path.join(self.eps, 'Scantraxx', 'UNKNOWN123 - Release')))
        self.assertEqual(os.listdir(self.imports), [])

    def test_the_cache_is_in_the_database_so_a_restart_does_not_resolve_again(self):
        self.release('UNKNOWN123 - Release')
        self.mover.run()

        self.new_mover().run()

        self.assertEqual(self.resolve.call_count, 1)

    def test_a_changed_catalogue_rule_resolves_every_unplaceable_folder_once_more(self):
        self.release('UNKNOWN123 - Release')
        self.release('OTHER456 - Release')
        self.mover.run()

        self.store.rules_version = '1:12345'
        self.mover.run()
        self.mover.run()

        self.assertEqual(self.resolve.call_count, 4)

    def test_a_decision_on_the_proposal_resolves_that_folder_once_more(self):
        self.release('UNKNOWN123 - Release')
        self.release('OTHER456 - Release')
        self.mover.run()

        self.store.decide('UNKNOWN123 - Release', 'rejected', '2026-09-24 12:00:00')
        self.mover.run()
        self.mover.run()

        self.assertEqual(self.resolve.call_count, 3)
        self.assertEqual(self.resolve.call_args.args[0], os.path.join(self.imports, 'UNKNOWN123 - Release'))

    def test_a_deleted_proposal_row_is_written_again(self):
        self.release('UNKNOWN123 - Release')
        self.mover.run()

        self.store.rows.clear()
        self.mover.run()

        self.assertEqual(self.store.record.call_count, 2)
        self.assertIn('UNKNOWN123 - Release', self.store.rows)

    def test_a_changed_mtime_alone_resolves_again(self):
        path = self.release('UNKNOWN123 - Release')
        self.mover.run()

        os.utime(os.path.join(path, '01.mp3'), (AN_HOUR_AGO + 60, AN_HOUR_AGO + 60))
        self.mover.run()

        self.assertEqual(self.resolve.call_count, 2)

    def test_without_the_database_the_process_memory_still_skips(self):
        self.release('UNKNOWN123 - Release')
        self.store.unreachable = True

        self.mover.run()
        self.mover.run()

        self.assertEqual(self.resolve.call_count, 1)

    def test_a_folder_that_cannot_be_read_is_resolved_every_time(self):
        self.release('UNKNOWN123 - Release')
        with patch.object(mover_module, 'folder_signature', return_value=None):
            self.mover.run()
            self.mover.run()

        self.assertEqual(self.resolve.call_count, 2)

    def test_one_count_line_per_cycle_and_the_warning_only_on_a_re_read(self):
        self.release('UNKNOWN123 - Release')
        self.release('NoCatalogNumber')
        self.mover.run()

        with self.assertLogs(level='DEBUG') as logs:
            self.mover.run()

        warnings = [r for r in logs.records if r.levelname == 'WARNING']
        counts = [r.getMessage() for r in logs.records if r.getMessage().startswith('Unplaceable folders:')]
        self.assertEqual(warnings, [])
        self.assertEqual(counts, ['Unplaceable folders: 2 checked, 2 skipped as unchanged, 0 re-read'])

    def test_the_first_cycle_warns_per_folder_and_counts_the_re_reads(self):
        self.release('UNKNOWN123 - Release')

        with self.assertLogs(level='DEBUG') as logs:
            self.mover.run()

        messages = [r.getMessage() for r in logs.records]
        self.assertTrue(any('CAT ID UNKNOWN not found' in m for m in messages), messages)
        self.assertIn('Unplaceable folders: 1 checked, 0 skipped as unchanged, 1 re-read', messages)


class OnePushPerReleaseTest(MoverOnDiskTest):
    def test_a_release_is_one_push_with_label_catalogue_and_track_count(self):
        self.release('SCAN123 - Artist_-_Title-(SCAN123)-WEB-2026', tracks=('01.mp3', '02.mp3', '03.mp3'))
        self.mover.get_label.return_value = 'Scantraxx'

        with patch.object(mover_module, 'post_processing_songs', return_value=3):
            self.mover.run()

        self.notify.assert_called_once()
        message = self.notify.call_args.args[0]
        self.assertIn('Label: Scantraxx', message)
        self.assertIn('Catalog: SCAN123', message)
        self.assertIn('Tracks: 3', message)
        self.assertEqual(self.notify.call_args.kwargs['title'], 'Import Complete')
        self.assertNotIn('push', self.notify.call_args.kwargs)

    def test_a_pack_of_releases_is_one_push_each_not_one_per_file(self):
        for number in range(1, 5):
            self.release(f'SCAN12{number} - Release {number}', tracks=('01.mp3', '02.mp3'))
        self.mover.get_label.return_value = 'Scantraxx'

        with patch.object(mover_module, 'LabelSong'), patch.object(mover_module, 'announce'):
            self.mover.run()

        pushes = [call for call in self.notify.call_args_list if call.kwargs.get('push', True)]
        quiet = [call for call in self.notify.call_args_list if call.kwargs.get('push') is False]
        self.assertEqual(len(pushes), 4)
        self.assertEqual(len(quiet), 8)

    def test_a_dry_run_pushes_nothing(self):
        self.release('SCAN123 - Release')
        self.mover.get_label.return_value = 'Scantraxx'

        with patch.object(mover_module, 'post_processing_songs', return_value=0):
            self.mover.run(dry_run=True)

        self.notify.assert_not_called()

    def test_a_release_that_went_nowhere_pushes_nothing(self):
        self.release('SCAN123 - Release')
        self.mover.get_label.return_value = 'Scantraxx'

        with patch.object(mover_module.shutil, 'move', side_effect=PermissionError('read only')):
            self.mover.run()

        self.notify.assert_not_called()


class ReleaseSummaryTest(unittest.TestCase):
    def test_a_folder_without_the_renamers_separator_has_no_catalogue_line(self):
        summary = release_summary('Loose Release', 'Scantraxx', 2)
        self.assertNotIn('Catalog', summary)
        self.assertIn('Tracks: 2', summary)


if __name__ == '__main__':
    unittest.main()
