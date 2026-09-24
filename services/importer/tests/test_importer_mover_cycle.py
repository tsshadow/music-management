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

from services.tests.connector_fakes import fake_connector
from services.tests.mock_base import reset_database_helpers, setup_mocks

setup_mocks()
from services.importer import mover as mover_module  # noqa: E402
from services.importer import settle  # noqa: E402
from services.importer.label_resolver import LabelProposal  # noqa: E402
from services.importer.mover import Mover, release_summary  # noqa: E402

AN_HOUR_AGO = time.time() - 3600


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
        self.mover = Mover()
        self.mover.proposals = MagicMock()
        self.mover.get_label = MagicMock(return_value=None)

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

    def test_the_cache_lives_in_the_process_so_a_restart_resolves_once_more(self):
        self.release('UNKNOWN123 - Release')
        self.mover.run()

        restarted = Mover()
        restarted.proposals = MagicMock()
        restarted.get_label = MagicMock(return_value=None)
        restarted.run()

        self.assertEqual(self.resolve.call_count, 2)


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
