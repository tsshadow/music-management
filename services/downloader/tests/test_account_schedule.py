import unittest
from datetime import datetime, timedelta

from services.tests.mock_base import setup_mocks
setup_mocks()

from services.downloader.account_schedule import (
    AccountSchedule,
    InMemoryCheckStore,
    due_accounts,
)

NOW = datetime(2026, 7, 30, 12, 0, 0)


class DueAccountsTest(unittest.TestCase):

    def test_an_account_that_was_never_checked_is_due(self):
        self.assertEqual(due_accounts(['dj_a'], {}, cooldown=3600, now=NOW), ['dj_a'])

    def test_an_account_checked_within_the_cooldown_is_skipped(self):
        checked = {'dj_a': NOW - timedelta(seconds=60)}
        self.assertEqual(due_accounts(['dj_a'], checked, cooldown=3600, now=NOW), [])

    def test_an_account_checked_before_the_cooldown_is_due_again(self):
        checked = {'dj_a': NOW - timedelta(seconds=3601)}
        self.assertEqual(due_accounts(['dj_a'], checked, cooldown=3600, now=NOW), ['dj_a'])

    def test_a_zero_cooldown_lets_everything_through(self):
        checked = {'dj_a': NOW}
        self.assertEqual(due_accounts(['dj_a'], checked, cooldown=0, now=NOW), ['dj_a'])

    def test_the_order_of_the_accounts_is_kept(self):
        checked = {'dj_b': NOW - timedelta(seconds=10)}
        due = due_accounts(['dj_a', 'dj_b', 'dj_c'], checked, cooldown=3600, now=NOW)
        self.assertEqual(due, ['dj_a', 'dj_c'])

    def test_a_check_stamped_in_the_future_still_blocks(self):
        checked = {'dj_a': NOW + timedelta(hours=1)}
        self.assertEqual(due_accounts(['dj_a'], checked, cooldown=3600, now=NOW), [])

    def test_accounts_that_were_never_seen_are_not_invented(self):
        checked = {'dj_gone': NOW - timedelta(days=9)}
        self.assertEqual(due_accounts(['dj_a'], checked, cooldown=3600, now=NOW), ['dj_a'])


class AccountScheduleTest(unittest.TestCase):

    def setUp(self):
        self.store = InMemoryCheckStore()
        self.now = NOW
        self.schedule = AccountSchedule('soundcloud', store=self.store, now=lambda: self.now)

    def test_all_accounts_are_due_on_a_fresh_install(self):
        self.assertEqual(self.schedule.due(['dj_a', 'dj_b'], cooldown=3600), ['dj_a', 'dj_b'])

    def test_a_checked_account_drops_out_until_the_cooldown_passes(self):
        self.schedule.mark_checked('dj_a')
        self.assertEqual(self.schedule.due(['dj_a', 'dj_b'], cooldown=3600), ['dj_b'])

    def test_the_account_returns_once_the_cooldown_has_passed(self):
        self.schedule.mark_checked('dj_a')
        self.now = NOW + timedelta(seconds=3601)
        self.assertEqual(self.schedule.due(['dj_a'], cooldown=3600), ['dj_a'])

    def test_marking_the_same_account_twice_just_moves_the_timestamp(self):
        self.schedule.mark_checked('dj_a')
        self.now = NOW + timedelta(seconds=1800)
        self.schedule.mark_checked('dj_a')
        self.now = NOW + timedelta(seconds=3601)
        self.assertEqual(self.schedule.due(['dj_a'], cooldown=3600), [])

    def test_sources_do_not_share_their_schedule(self):
        self.schedule.mark_checked('dj_a')
        other = AccountSchedule('youtube', store=self.store, now=lambda: self.now)
        self.assertEqual(other.due(['dj_a'], cooldown=3600), ['dj_a'])


class AccountScheduleSurvivesStorageFailureTest(unittest.TestCase):

    class BrokenStore:

        def load(self, source):
            raise RuntimeError('database is down')

        def mark(self, source, account, when):
            raise RuntimeError('database is down')

    def test_everything_is_due_when_the_store_cannot_be_read(self):
        schedule = AccountSchedule('soundcloud', store=self.BrokenStore(), now=lambda: NOW)
        self.assertEqual(schedule.due(['dj_a'], cooldown=3600), ['dj_a'])

    def test_marking_a_check_does_not_raise_when_the_store_is_down(self):
        schedule = AccountSchedule('soundcloud', store=self.BrokenStore(), now=lambda: NOW)
        schedule.mark_checked('dj_a')


if __name__ == '__main__':
    unittest.main()
