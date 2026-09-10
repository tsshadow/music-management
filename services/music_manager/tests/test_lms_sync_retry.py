"""Coming back when the server was still migrating.

A deploy restarts both services at once and muma usually wins the race: it syncs before
the server has applied its own schema migration, finds no version columns, and skips.
Skipping is right -- writing into a schema mid-migration is the one thing not to do --
but nothing came back afterwards, so the columns stayed empty until somebody restarted
the container by hand. That is exactly what happened on the 0.54.0 deploy, and without
the restart the release would have shipped a feature that silently did nothing.

What is pinned here is narrow: it comes back while a database was skipped for that one
reason, and it does not come back for anything else.
"""

import unittest
from unittest.mock import MagicMock, patch

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.music_manager.routers import users  # noqa: E402


class LmsSyncRetryTest(unittest.TestCase):
    def setUp(self):
        users._skipped_unmigrated_servers.clear()
        self.addCleanup(users._skipped_unmigrated_servers.clear)
        sleep = patch.object(users.time, 'sleep')
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)

    def test_a_ready_server_is_synced_once(self):
        with patch.object(users, 'run_lms_db_sync', return_value=3) as sync:
            self.assertEqual(users.run_lms_db_sync_with_retry(), 3)
        sync.assert_called_once()
        self.sleep.assert_not_called()

    def test_a_server_that_is_still_migrating_gets_another_pass(self):
        calls = []

        def sync():
            calls.append(1)
            # Ready on the third attempt, which is what a server restart looks like.
            if len(calls) < 3:
                users._skipped_unmigrated_servers.add('server-stable')
            else:
                users._skipped_unmigrated_servers.clear()
            return 0

        with patch.object(users, 'run_lms_db_sync', side_effect=sync):
            users.run_lms_db_sync_with_retry(attempts=5, delay_seconds=1)

        self.assertEqual(len(calls), 3)

    def test_it_gives_up_rather_than_retrying_forever(self):
        def sync():
            users._skipped_unmigrated_servers.add('server-stable')
            return 0

        with patch.object(users, 'run_lms_db_sync', side_effect=sync):
            users.run_lms_db_sync_with_retry(attempts=3, delay_seconds=1)

        self.assertEqual(self.sleep.call_count, 2, 'no sleep after the last attempt')

    def test_the_skip_is_recorded_only_for_an_unmigrated_server(self):
        # A locked database, an unreachable server, no lms.db at all: all best-effort
        # inside the sync itself, and none of them a reason to come back here.
        connection = MagicMock()
        with (
            patch.object(users, 'sqlite3') as sqlite,
            patch('services.music_manager.song_version_sync.sync_song_versions_to_server') as versions,
            patch('services.music_manager.routers.artist_images.sync_artist_images_to_server'),
            patch.object(users, '_sync_server_users', return_value=0),
            patch.object(users, '_sync_server_playlists'),
        ):
            sqlite.connect.return_value = connection
            versions.return_value = {'considered': 10, 'matched': 10, 'skipped_no_columns': 0}
            users.sync_single_server_db(MagicMock(), '/app/data/stable/lms.db', 'server-stable')
        self.assertEqual(users._skipped_unmigrated_servers, set())

    def test_an_unmigrated_server_is_remembered_by_name(self):
        connection = MagicMock()
        with (
            patch.object(users, 'sqlite3') as sqlite,
            patch('services.music_manager.song_version_sync.sync_song_versions_to_server') as versions,
            patch('services.music_manager.routers.artist_images.sync_artist_images_to_server'),
            patch.object(users, '_sync_server_users', return_value=0),
            patch.object(users, '_sync_server_playlists'),
        ):
            sqlite.connect.return_value = connection
            versions.return_value = {'considered': 0, 'matched': 0, 'skipped_no_columns': 1}
            users.sync_single_server_db(MagicMock(), '/app/data/alpha/lms.db', 'server-alpha')
        self.assertEqual(users._skipped_unmigrated_servers, {'server-alpha'})


if __name__ == '__main__':
    unittest.main()
