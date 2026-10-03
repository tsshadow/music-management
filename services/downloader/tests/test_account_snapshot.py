"""The count a deep pass leaves behind: how complete an account is, stored."""

import unittest
from datetime import datetime, timedelta
from typing import Any
from unittest import mock

import pytest

from services.downloader.account_schedule import AccountSchedule, DatabaseCheckStore, InMemoryCheckStore
from services.downloader.deep_sweep import (
    SNAPSHOT_CAPPED,
    SNAPSHOT_COMPLETE,
    SNAPSHOT_PARKED,
    AccountSnapshot,
    DeepSweepReport,
    FlatTrack,
    snapshot_state,
    take_snapshot,
)
from services.downloader.rate_state import InMemoryRateStateStore, RateLimited, RateState
from services.downloader.soundcloud.soundcloud import SoundcloudDownloader
from services.downloader.timing import load_timing
from services.downloader.write_offs import InMemoryWriteOffStore, WriteOff, WriteOffs

pytestmark = pytest.mark.mock_base('yt_dlp')

NOW = datetime(2026, 9, 21, 12, 0, 0)
DAY = timedelta(days=1)
BOUNDS = (60, 21600)


def track(track_id: str) -> FlatTrack:
    return FlatTrack(track_id=track_id, url=f'https://example.test/{track_id}', title=track_id)


def listing(*ids):
    return [track(track_id) for track_id in ids]


def report(**overrides) -> DeepSweepReport:
    values: dict[str, Any] = {'listed': 0, 'held': 0, 'written_off': 0, 'wanted': 0}
    values.update(overrides)
    return DeepSweepReport(**values)


def snapshot(tracks, held=frozenset(), arrived=frozenset(), write_offs=None, state=SNAPSHOT_COMPLETE, bounds=BOUNDS):
    return take_snapshot(tracks, set(held), set(arrived), write_offs or {}, 30, NOW, bounds, state)


class TakeSnapshotTest(unittest.TestCase):
    """Every listed id lands in exactly one of held, excluded and remaining."""

    def test_the_three_parts_add_up_to_the_listing(self):
        offs = {'c': WriteOff('too_short', NOW, 30, 0)}
        result = snapshot(listing('a', 'b', 'c', 'd'), held={'a'}, arrived={'b'}, write_offs=offs)
        self.assertEqual((4, 2, 1, 1), (result.listed, result.held, result.excluded, result.remaining))

    def test_what_arrived_during_the_pass_is_held_now(self):
        result = snapshot(listing('a'), held=set(), arrived={'a'})
        self.assertEqual(1, result.held)
        self.assertEqual(0, result.remaining)

    def test_an_id_in_the_archive_but_not_in_the_listing_is_not_counted(self):
        # The text archive can name tracks the platform no longer lists; they are
        # not part of the account as it stands today.
        result = snapshot(listing('a'), held={'a', 'gone'})
        self.assertEqual(1, result.listed)
        self.assertEqual(1, result.held)

    def test_an_id_both_held_and_written_off_counts_as_held(self):
        offs = {'a': WriteOff('403', NOW, None, 0)}
        result = snapshot(listing('a'), held={'a'}, write_offs=offs)
        self.assertEqual((1, 0, 0), (result.held, result.excluded, result.remaining))

    def test_a_failure_recorded_this_pass_is_excluded(self):
        # `failing` after one attempt keeps the track out for the retry window,
        # which is what the next pass will see; so it is what gets stored.
        offs = {'a': WriteOff('failing', NOW, None, 1)}
        result = snapshot(listing('a'), write_offs=offs)
        self.assertEqual(1, result.excluded)
        self.assertEqual(0, result.remaining)

    def test_an_expired_write_off_is_remaining_again(self):
        offs = {'a': WriteOff('403', NOW - 31 * DAY, None, 0)}
        result = snapshot(listing('a'), write_offs=offs)
        self.assertEqual(0, result.excluded)
        self.assertEqual(1, result.remaining)

    def test_a_duration_verdict_is_re_formed_from_the_current_bounds(self):
        offs = {'a': WriteOff('too_short', NOW, 30, 0)}
        widened = snapshot(listing('a'), write_offs=offs, bounds=(10, 21600))
        self.assertEqual(1, widened.remaining)

    def test_a_repeated_id_is_counted_once(self):
        result = snapshot(listing('a', 'a', 'b'), held={'a'})
        self.assertEqual((2, 1, 0, 1), (result.listed, result.held, result.excluded, result.remaining))

    def test_the_state_follows_how_the_pass_ended(self):
        self.assertEqual(SNAPSHOT_PARKED, snapshot_state(report(parked=True, capped=True)))
        self.assertEqual(SNAPSHOT_CAPPED, snapshot_state(report(capped=True)))
        self.assertEqual(SNAPSHOT_COMPLETE, snapshot_state(report()))

    def test_a_stop_request_counts_as_not_reaching_the_end(self):
        self.assertEqual(SNAPSHOT_PARKED, snapshot_state(report(), interrupted=True))

    def test_the_state_given_is_the_state_stored(self):
        self.assertEqual(SNAPSHOT_CAPPED, snapshot([], state=SNAPSHOT_CAPPED).state)

    def test_the_snapshot_carries_the_time_it_was_taken(self):
        self.assertEqual(NOW, snapshot([]).taken_at)

    def test_coverage_is_held_over_listed(self):
        result = snapshot(listing('a', 'b', 'c', 'd'), held={'a', 'b', 'c'})
        self.assertEqual(0.75, result.coverage)

    def test_an_empty_listing_has_no_coverage(self):
        # Zero of zero is not "complete"; it is an account we know nothing about.
        self.assertIsNone(snapshot([]).coverage)


def a_snapshot(**overrides) -> AccountSnapshot:
    values: dict[str, Any] = {
        'listed': 10,
        'held': 7,
        'excluded': 1,
        'remaining': 2,
        'state': SNAPSHOT_CAPPED,
        'taken_at': NOW,
    }
    values.update(overrides)
    return AccountSnapshot(**values)


class InMemoryStoreSnapshotTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryCheckStore()
        self.schedule = AccountSchedule('soundcloud', store=self.store, now=lambda: NOW)

    def _record(self, account='dj_a'):
        return self.store.load('soundcloud')[account]

    def test_a_snapshot_is_stored_beside_the_check(self):
        self.schedule.mark_checked('dj_a', last_upload_at=NOW - DAY, last_seen_track_id='1')
        self.schedule.record_snapshot('dj_a', a_snapshot())
        record = self._record()
        self.assertEqual(a_snapshot(), record.snapshot)
        self.assertEqual(NOW, record.last_checked_at)
        self.assertEqual(NOW - DAY, record.last_upload_at)
        self.assertEqual('1', record.last_seen_track_id)

    def test_an_account_never_checked_gets_a_row_from_its_snapshot(self):
        self.schedule.record_snapshot('dj_a', a_snapshot())
        record = self._record()
        self.assertEqual(NOW, record.last_checked_at)
        self.assertIsNone(record.last_deep_sweep_at)

    def test_a_later_check_keeps_the_snapshot(self):
        self.schedule.record_snapshot('dj_a', a_snapshot())
        self.schedule.mark_checked('dj_a')
        self.schedule.mark_deep_swept('dj_a')
        self.assertEqual(a_snapshot(), self._record().snapshot)

    def test_a_newer_snapshot_replaces_the_old_one(self):
        self.schedule.record_snapshot('dj_a', a_snapshot(remaining=2))
        self.schedule.record_snapshot('dj_a', a_snapshot(remaining=0, state=SNAPSHOT_COMPLETE))
        self.assertEqual(0, self._record().snapshot.remaining)

    def test_no_snapshot_until_a_deep_pass_ran(self):
        self.schedule.mark_checked('dj_a')
        self.assertIsNone(self._record().snapshot)

    def test_a_store_that_is_down_does_not_stop_the_sweep(self):
        class BrokenStore:
            def mark_snapshot(self, *args):
                raise RuntimeError('db down')

        AccountSchedule('soundcloud', store=BrokenStore()).record_snapshot('dj_a', a_snapshot())


class FakeCursor:
    def __init__(self, rows):
        self.rows = rows
        self.queries = []

    def execute(self, query, params=None):
        self.queries.append((query, params))

    def fetchall(self):
        return self.rows

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False


class FakeConnection:
    def __init__(self, rows=()):
        self.fake_cursor = FakeCursor(list(rows))
        self.committed = False

    def cursor(self):
        return self.fake_cursor

    def commit(self):
        self.committed = True

    def close(self):
        pass


class DatabaseStoreSnapshotTest(unittest.TestCase):
    def _store(self, rows=()):
        store = DatabaseCheckStore()
        self.connection = FakeConnection(rows)
        mock.patch.object(store, '_connect', return_value=self.connection).start()
        self.addCleanup(mock.patch.stopall)
        return store

    def test_the_six_columns_are_read_back_as_a_snapshot(self):
        store = self._store(rows=[('dj_a', NOW, None, None, None, 10, 7, 1, 2, 'capped', NOW)])
        record = store.load('soundcloud')['dj_a']
        self.assertEqual(a_snapshot(), record.snapshot)

    def test_a_row_that_predates_the_count_has_no_snapshot(self):
        store = self._store(rows=[('dj_a', NOW, None, None, None, None, None, None, None, None, None)])
        self.assertIsNone(store.load('soundcloud')['dj_a'].snapshot)

    def test_the_upsert_moves_only_the_snapshot_columns(self):
        store = self._store()
        store.mark_snapshot('soundcloud', 'dj_a', a_snapshot())
        query, params = self.connection.fake_cursor.queries[-1]
        self.assertIn('ON DUPLICATE KEY UPDATE', query)
        updated = query.split('ON DUPLICATE KEY UPDATE', 1)[1]
        self.assertNotIn('last_checked_at', updated)
        self.assertNotIn('last_deep_sweep_at', updated)
        self.assertIn('snapshot_remaining = VALUES(snapshot_remaining)', updated)
        self.assertEqual(('soundcloud', 'dj_a', NOW, 10, 7, 1, 2, 'capped', NOW), params)
        self.assertTrue(self.connection.committed)


class StubNotifier:
    def notify(self, message, title='Music Management'):
        return None


class SoundcloudPassSnapshotTest(unittest.TestCase):
    """The SoundCloud pass writes the same count the YouTube one does."""

    def setUp(self):
        mock.patch('os.makedirs').start()
        self.addCleanup(mock.patch.stopall)
        timing = load_timing('soundcloud', overrides={'deep_sweep_max_downloads': 2})
        self.check_store = InMemoryCheckStore()
        self.downloader = SoundcloudDownloader(
            timing=timing,
            rate_state=RateState('soundcloud', timing, store=InMemoryRateStateStore()),
            schedule=AccountSchedule('soundcloud', store=self.check_store),
            notifier=StubNotifier(),
            unavailable=WriteOffs('soundcloud', store=InMemoryWriteOffStore(), retry_days=30),
        )
        self.downloader.downloader_config['archive_file'] = None
        self.downloader.downloader_config['archive_dir'] = '/nonexistent'
        self.downloader.download_url = lambda url, ydl_opts=None, account=None: None

    def _sweep(self, tracks, held, held_after):
        with (
            mock.patch('services.downloader.soundcloud.soundcloud.list_flat', return_value=tracks),
            mock.patch(
                'services.downloader.soundcloud.soundcloud.SoundcloudArchive.held_ids', side_effect=[held, held_after]
            ),
        ):
            return self.downloader.deep_sweep_account('dj_a', {})

    def _snapshot(self):
        return self.check_store.load('soundcloud')['dj_a'].snapshot

    def test_a_finished_pass_is_counted(self):
        self._sweep(listing('a', 'b'), held={'a'}, held_after={'a', 'b'})
        result = self._snapshot()
        self.assertEqual((2, 2, 0, 0), (result.listed, result.held, result.excluded, result.remaining))
        self.assertEqual(SNAPSHOT_COMPLETE, result.state)

    def test_a_capped_pass_leaves_the_tail_remaining(self):
        self._sweep(listing('a', 'b', 'c'), held=set(), held_after={'a', 'b'})
        result = self._snapshot()
        self.assertEqual(SNAPSHOT_CAPPED, result.state)
        self.assertEqual(1, result.remaining)

    def test_a_rate_limit_mid_batch_still_leaves_a_count(self):
        def _limited(url, ydl_opts=None, account=None):
            raise RateLimited('soundcloud', 600, '429')

        self.downloader.download_url = _limited
        with self.assertRaises(RateLimited):
            self._sweep(listing('a', 'b'), held=set(), held_after=set())
        result = self._snapshot()
        self.assertEqual(SNAPSHOT_PARKED, result.state)
        # Nothing was written off by a parked pass, so both are still to fetch.
        self.assertEqual((2, 0, 0, 2), (result.listed, result.held, result.excluded, result.remaining))


class ManagerWithoutYtDlpTest(unittest.TestCase):
    """The manager container has no yt-dlp; reading a snapshot must not need it.

    Run in a subprocess with `yt_dlp` made unimportable, because this process has
    long since imported it. The first evening the page was live it answered
    "No module named 'yt_dlp'" for exactly this reason.
    """

    def test_a_stored_row_is_read_without_yt_dlp(self):
        import subprocess
        import sys

        script = (
            'import sys; sys.modules["yt_dlp"] = None\n'
            'from datetime import datetime\n'
            'from services.downloader.account_schedule import _snapshot_from_row\n'
            'from services.music_manager import downloader_coverage\n'
            'snapshot = _snapshot_from_row((10, 7, 1, 2, "capped", datetime(2026, 9, 21)))\n'
            'assert snapshot.remaining == 2, snapshot\n'
            'print("ok")\n'
        )
        result = subprocess.run([sys.executable, '-c', script], capture_output=True, text=True, check=False)
        self.assertEqual(0, result.returncode, result.stderr)
        self.assertIn('ok', result.stdout)


if __name__ == '__main__':
    unittest.main()
