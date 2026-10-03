"""The mover deletes a queue folder that holds no audio instead of placing it (GitLab issue #167).

A release whose tracks are gone keeps its `00-*.m3u`, `.nfo`, `.sfv` and cover. Placed in the
label tree, LMS would report its playlist as missing entries after every scan. Judged on a real
import folder: such a folder goes, with an event and an LMS rescan; a folder with audio at any
depth, with an archive not yet extracted, or still being copied in, is left to the usual path.
"""

import os
import time
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('Cache')

from services.common import audio_less_folder  # noqa: E402
from services.importer import mover as mover_module  # noqa: E402
from services.importer import settle  # noqa: E402
from services.importer.tests.test_importer_mover_cycle import MoverOnDiskTest  # noqa: E402


class AudioLessQueueFolderTest(MoverOnDiskTest):
    def setUp(self):
        super().setUp()
        self.store.mark_gone = MagicMock()
        self.lms = self.enterContext(patch.object(mover_module, 'lms_scan_trigger'))
        self.mover.get_label = MagicMock(return_value='Scantraxx')
        self.post = self.enterContext(patch.object(mover_module, 'post_processing_songs', return_value=1))

    def placed(self, folder):
        return os.path.isdir(os.path.join(self.eps, 'Scantraxx', folder))

    def test_a_folder_with_only_scene_files_is_deleted_not_placed(self):
        folder = 'HCL116 - Double_Phunq_-_Wizard-(HCL116)-SINGLE-WEB-2026-SRG'
        path = self.release(folder, tracks=('00-wizard.jpg', '00-wizard.m3u'))

        self.mover.run()

        self.assertFalse(os.path.exists(path))
        self.assertFalse(self.placed(folder))
        self.post.assert_not_called()

    def test_the_delete_is_an_event_without_a_push_and_an_lms_rescan(self):
        folder = 'HCL116 - Release'
        path = self.release(folder, tracks=('00-r.jpg', '00-r.m3u'))

        self.mover.run()

        self.notify.assert_called_once()
        message = self.notify.call_args.args[0]
        self.assertIn(folder, message)
        self.assertIn('00-r.jpg, 00-r.m3u', message)
        self.assertEqual(self.notify.call_args.kwargs['push'], False)
        self.lms.notify.assert_called_once_with([path])
        self.store.mark_gone.assert_called_once_with(folder)

    def test_a_folder_without_a_catalogue_number_is_deleted_too(self):
        path = self.release('Peygan_and_Schlot_-_Hey_Baby-WEB-2026', tracks=('00_hey_baby.m3u',))

        self.mover.run()

        self.assertFalse(os.path.exists(path))
        self.resolve.assert_not_called()

    def test_a_folder_with_audio_is_placed_as_before(self):
        folder = 'SCAN123 - Release'
        self.release(folder, tracks=('00-r.m3u', '01-track.mp3'))

        self.mover.run()

        self.assertTrue(self.placed(folder))
        self.store.mark_gone.assert_not_called()

    def test_a_folder_whose_audio_sits_in_disc_folders_is_placed_as_before(self):
        folder = 'SCAN123 - Release'
        path = self.release(folder, tracks=('00-r.nfo',))
        os.makedirs(os.path.join(path, 'CD1'))
        with open(os.path.join(path, 'CD1', '01-track.flac'), 'w', encoding='utf-8') as handle:
            handle.write('audio')

        self.mover.run()

        self.assertTrue(os.path.isfile(os.path.join(self.eps, 'Scantraxx', folder, 'CD1', '01-track.flac')))

    def test_a_folder_with_an_archive_not_yet_extracted_is_not_deleted(self):
        folder = 'UNKNOWN123 - Release'
        self.mover.get_label = MagicMock(return_value=None)
        path = self.release(folder, tracks=('00-r.nfo', 'release.rar'))

        self.mover.run()

        self.assertTrue(os.path.isfile(os.path.join(path, 'release.rar')))
        self.store.mark_gone.assert_not_called()

    def test_a_folder_still_being_copied_in_is_left_alone(self):
        path = self.release('HCL116 - Release', tracks=('00-r.m3u',))
        os.utime(path, (time.time(), time.time()))

        with patch.object(settle, 'settle_seconds', return_value=300):
            self.mover.run()

        self.assertTrue(os.path.isdir(path))

    def test_a_dry_run_deletes_nothing_and_says_so(self):
        path = self.release('HCL116 - Release', tracks=('00-r.m3u',))

        with self.assertLogs(level='INFO') as logs:
            self.mover.run(dry_run=True)

        self.assertTrue(os.path.isdir(path))
        self.notify.assert_not_called()
        self.assertTrue(any('would delete HCL116 - Release' in line for line in logs.output))

    def test_a_folder_that_cannot_be_deleted_is_still_not_placed(self):
        folder = 'HCL116 - Release'
        path = self.release(folder, tracks=('00-r.m3u',))

        with (
            patch.object(audio_less_folder.shutil, 'rmtree', side_effect=PermissionError('denied')),
            self.assertLogs(level='ERROR') as logs,
        ):
            self.mover.run()

        self.assertTrue(os.path.isdir(path))
        self.assertFalse(self.placed(folder))
        self.notify.assert_not_called()
        self.assertTrue(any('denied' in line for line in logs.output))

    def test_a_queue_elsewhere_than_the_import_folder_refuses_the_delete(self):
        path = self.release('HCL116 - Release', tracks=('00-r.m3u',))
        other_queue = os.path.join(self.root, 'other-queue')
        os.makedirs(other_queue)

        with (
            patch.object(mover_module.ImportQueue, 'from_settings', return_value=mover_module.ImportQueue(other_queue)),
            self.assertLogs(level='WARNING') as logs,
        ):
            self.mover.run()

        self.assertTrue(os.path.isdir(path))
        self.assertFalse(self.placed('HCL116 - Release'))
        self.assertTrue(any('not a folder in the import queue' in line for line in logs.output))
