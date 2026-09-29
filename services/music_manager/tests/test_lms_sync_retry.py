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

import os
import sqlite3
import tempfile
import unittest
from unittest.mock import MagicMock, patch

from services.music_manager import lms_writes
from services.music_manager.lms_writes import PendingWrites
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

        def sync(only_sources=None):
            calls.append(only_sources)
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
        def sync(only_sources=None):
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


class RetryScopeTest(unittest.TestCase):
    """A retry must cost only the server it is waiting for.

    Production ran the full pass six times an hour: a second LMS instance sits on an old
    schema and never becomes ready, so every attempt walked all 285.360 tracks again --
    including for the server that had just been written correctly.
    """

    def setUp(self):
        users._skipped_unmigrated_servers.clear()
        self.addCleanup(users._skipped_unmigrated_servers.clear)
        sleep = patch.object(users.time, 'sleep')
        sleep.start()
        self.addCleanup(sleep.stop)

    def test_a_retry_names_only_the_server_that_was_skipped(self):
        calls = []

        def sync(only_sources=None):
            calls.append(only_sources)
            users._skipped_unmigrated_servers.clear()
            users._skipped_unmigrated_servers.add('server-alpha')
            return 0

        with patch.object(users, 'run_lms_db_sync', side_effect=sync):
            users.run_lms_db_sync_with_retry(attempts=3, delay_seconds=1)

        self.assertIsNone(calls[0], 'the first pass covers every server')
        self.assertTrue(all(c == {'server-alpha'} for c in calls[1:]), calls)

    def test_a_server_that_is_ready_is_not_walked_again(self):
        calls = []

        def sync(only_sources=None):
            calls.append(only_sources)
            users._skipped_unmigrated_servers.clear()
            return 5

        with patch.object(users, 'run_lms_db_sync', side_effect=sync):
            self.assertEqual(users.run_lms_db_sync_with_retry(attempts=6, delay_seconds=1), 5)

        self.assertEqual(len(calls), 1, 'nothing was skipped, so nothing is retried')


class DeferredWritesRetryTest(unittest.TestCase):
    """Rows a busy server refused are written a few minutes later, not an hour later or never.

    Bug report 129: an LMS scan holds the server's write lock for hours, and the pass used to
    sleep through it batch by batch and then drop what it could not write with a WARNING -- 40
    a day. Now the pass defers those rows and this retry writes exactly them. What is pinned:
    they land once the server lets go, a server that stays busy costs one WARNING per cycle
    rather than one per batch, and the pass that follows starts from a clean slate.
    """

    def setUp(self):
        users._deferred_writes.clear()
        self.addCleanup(users._deferred_writes.clear)
        sleep = patch.object(users.time, 'sleep')
        self.sleep = sleep.start()
        self.addCleanup(sleep.stop)
        directory = tempfile.mkdtemp()
        self.path = os.path.join(directory, 'lms.db')
        setup = sqlite3.connect(self.path)
        setup.execute('PRAGMA journal_mode=WAL')
        setup.execute("CREATE TABLE track (id INTEGER PRIMARY KEY, form TEXT NOT NULL DEFAULT '')")
        setup.executemany('INSERT INTO track (id) VALUES (?)', [(1,), (2,)])
        setup.commit()
        setup.close()
        targets = patch.object(users, 'lms_db_targets', return_value=[(self.path, 'server-stable')])
        self.targets = targets.start()
        self.addCleanup(targets.stop)
        # Short, so a test that keeps the lock held does not wait ten seconds per try.
        timeout = patch.object(lms_writes, 'BUSY_TIMEOUT_STATEMENT', 'PRAGMA busy_timeout = 20')
        timeout.start()
        self.addCleanup(timeout.stop)

    def defer(self, *ids):
        writes = PendingWrites('UPDATE track SET form = ?1 WHERE id = ?2')
        writes.rows = [(('live_set',), track_id) for track_id in ids]
        writes.busy = True
        users._deferred_writes.setdefault('server-stable', []).append(writes)
        return writes

    def forms(self):
        conn = sqlite3.connect(self.path)
        try:
            return [row[0] for row in conn.execute('SELECT form FROM track ORDER BY id')]
        finally:
            conn.close()

    def run_retry(self, attempts=3):
        with patch.object(users, 'run_lms_db_sync', return_value=0):
            users.run_lms_db_sync_with_retry(deferred_attempts=attempts, deferred_delay_seconds=1)

    def test_the_deferred_rows_are_written_on_the_next_try(self):
        self.defer(1, 2)

        with self.assertLogs(level='INFO') as logs:
            self.run_retry()

        self.assertEqual(self.forms(), ['live_set', 'live_set'])
        self.assertEqual(self.sleep.call_count, 1)
        self.assertEqual(users._deferred_writes, {})
        self.assertTrue(any('wrote the 2 rows' in line for line in logs.output), logs.output)
        self.assertFalse([line for line in logs.output if line.startswith('WARNING')])

    def test_the_wait_before_a_try_carries_jitter_within_its_bound(self):
        self.defer(1)
        self.run_retry()
        (delay,), _ = self.sleep.call_args
        self.assertGreaterEqual(delay, 1)
        self.assertLessEqual(delay, 1 + users.DEFERRED_RETRY_JITTER_SECONDS)

    def test_a_server_that_stays_busy_costs_one_warning_and_keeps_nothing_stale(self):
        self.defer(1, 2)
        scanner = sqlite3.connect(self.path, isolation_level=None)
        self.addCleanup(scanner.close)
        scanner.execute('BEGIN IMMEDIATE')

        with self.assertLogs(level='WARNING') as logs:
            self.run_retry(attempts=3)
        scanner.execute('COMMIT')

        warnings = [line for line in logs.output if line.startswith('WARNING')]
        self.assertEqual(len(warnings), 1, warnings)
        self.assertIn('2 rows for server-stable', warnings[0])
        self.assertEqual(self.sleep.call_count, 3)
        self.assertEqual(self.forms(), ['', ''])
        self.assertEqual(users._deferred_writes, {}, 'the next hourly pass recomputes them')

    def test_nothing_deferred_means_no_wait(self):
        self.run_retry()
        self.sleep.assert_not_called()

    def test_a_server_that_went_away_is_dropped_without_a_warning(self):
        self.defer(1)
        self.targets.return_value = []

        with self.assertNoLogs(level='WARNING'):
            self.run_retry()

        self.assertEqual(users._deferred_writes, {})

    def test_a_new_pass_replaces_what_an_earlier_one_deferred(self):
        # The pass recomputes every difference, so the old list would only write stale values.
        # (Called directly: several test modules replace run_lms_db_sync at import time.)
        self.defer(1)
        users._deferred_writes['server-alpha'] = []
        users._discard_deferred_writes([(self.path, 'server-stable')])
        self.assertEqual(users._deferred_writes, {'server-alpha': []}, 'only the servers being synced')

    def test_both_pushes_hand_their_refusals_to_the_same_list(self):
        connection = MagicMock()
        connection.in_transaction = False
        with (
            patch.object(users, 'sqlite3') as sqlite,
            patch('services.music_manager.song_version_sync.sync_song_versions_to_server') as versions,
            patch('services.music_manager.track_form_sync.push_forms_to_server') as forms,
            patch('services.music_manager.routers.artist_images.sync_artist_images_to_server'),
            patch.object(users, '_sync_server_users', return_value=0),
            patch.object(users, '_sync_server_playlists'),
        ):
            sqlite.connect.return_value = connection
            versions.return_value = {'skipped_no_columns': 0}
            users.sync_single_server_db(MagicMock(), self.path, 'server-stable')

        collector = users._deferred_writes['server-stable']
        self.assertIs(versions.call_args.kwargs['deferred'], collector)
        self.assertIs(forms.call_args.kwargs['deferred'], collector)

    def test_a_transaction_the_image_sync_left_open_is_rolled_back_first(self):
        # Left open, it would hold the server's write lock through both pushes.
        connection = MagicMock()
        connection.in_transaction = True
        with (
            patch.object(users, 'sqlite3') as sqlite,
            patch('services.music_manager.song_version_sync.sync_song_versions_to_server') as versions,
            patch('services.music_manager.track_form_sync.push_forms_to_server'),
            patch('services.music_manager.routers.artist_images.sync_artist_images_to_server'),
            patch.object(users, '_sync_server_users', return_value=0),
            patch.object(users, '_sync_server_playlists'),
        ):
            sqlite.connect.return_value = connection
            versions.return_value = {'skipped_no_columns': 0}
            users.sync_single_server_db(MagicMock(), self.path, 'server-stable')

        connection.rollback.assert_called_once()


if __name__ == '__main__':
    unittest.main()
