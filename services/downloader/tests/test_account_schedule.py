import unittest
from datetime import datetime, timedelta

from services.tests.mock_base import setup_mocks

setup_mocks()

from services.downloader.account_schedule import (
    AccountCheck,
    AccountSchedule,
    InMemoryCheckStore,
    cooldown_for,
    due_accounts,
)
from services.downloader.timing import DownloaderTiming

NOW = datetime(2026, 7, 30, 12, 0, 0)


def checked_at(when):
    """One account's record, for the cases that only care about the check time."""
    return AccountCheck(last_checked_at=when)


class DueAccountsTest(unittest.TestCase):
    def test_an_account_that_was_never_checked_is_due(self):
        self.assertEqual(due_accounts(['dj_a'], {}, cooldown=3600, now=NOW), ['dj_a'])

    def test_an_account_checked_within_the_cooldown_is_skipped(self):
        checked = {'dj_a': checked_at(NOW - timedelta(seconds=60))}
        self.assertEqual(due_accounts(['dj_a'], checked, cooldown=3600, now=NOW), [])

    def test_an_account_checked_before_the_cooldown_is_due_again(self):
        checked = {'dj_a': checked_at(NOW - timedelta(seconds=3601))}
        self.assertEqual(due_accounts(['dj_a'], checked, cooldown=3600, now=NOW), ['dj_a'])

    def test_a_zero_cooldown_lets_everything_through(self):
        checked = {'dj_a': checked_at(NOW)}
        self.assertEqual(due_accounts(['dj_a'], checked, cooldown=0, now=NOW), ['dj_a'])

    def test_the_order_of_the_accounts_is_kept(self):
        checked = {'dj_b': checked_at(NOW - timedelta(seconds=10))}
        due = due_accounts(['dj_a', 'dj_b', 'dj_c'], checked, cooldown=3600, now=NOW)
        self.assertEqual(due, ['dj_a', 'dj_c'])

    def test_a_check_stamped_in_the_future_still_blocks(self):
        checked = {'dj_a': checked_at(NOW + timedelta(hours=1))}
        self.assertEqual(due_accounts(['dj_a'], checked, cooldown=3600, now=NOW), [])

    def test_accounts_that_were_never_seen_are_not_invented(self):
        checked = {'dj_gone': checked_at(NOW - timedelta(days=9))}
        self.assertEqual(due_accounts(['dj_a'], checked, cooldown=3600, now=NOW), ['dj_a'])


class CheckRecordTest(unittest.TestCase):
    """What the store remembers about an account beyond the last check time."""

    def setUp(self):
        self.store = InMemoryCheckStore()
        self.now = NOW
        self.schedule = AccountSchedule('soundcloud', store=self.store, now=lambda: self.now)

    def _record(self, account='dj_a'):
        return self.store.load('soundcloud')[account]

    def test_a_plain_check_records_only_the_time(self):
        self.schedule.mark_checked('dj_a')
        record = self._record()
        self.assertEqual(record.last_checked_at, NOW)
        self.assertIsNone(record.last_upload_at)
        self.assertIsNone(record.last_seen_track_id)

    def test_an_upload_date_is_recorded_when_it_is_known(self):
        uploaded = NOW - timedelta(days=2)
        self.schedule.mark_checked('dj_a', last_upload_at=uploaded, last_seen_track_id='2379459947')
        record = self._record()
        self.assertEqual(record.last_upload_at, uploaded)
        self.assertEqual(record.last_seen_track_id, '2379459947')

    def test_a_later_plain_check_does_not_erase_a_known_upload_date(self):
        # Writing NULL on every ordinary check would throw away the date and
        # force the account to be re-probed forever.
        uploaded = NOW - timedelta(days=2)
        self.schedule.mark_checked('dj_a', last_upload_at=uploaded, last_seen_track_id='2379459947')
        self.now = NOW + timedelta(hours=7)
        self.schedule.mark_checked('dj_a')
        record = self._record()
        self.assertEqual(record.last_checked_at, self.now)
        self.assertEqual(record.last_upload_at, uploaded)
        self.assertEqual(record.last_seen_track_id, '2379459947')

    def test_a_newer_upload_date_replaces_the_stored_one(self):
        self.schedule.mark_checked('dj_a', last_upload_at=NOW - timedelta(days=200), last_seen_track_id='old')
        newer = NOW - timedelta(hours=1)
        self.schedule.mark_checked('dj_a', last_upload_at=newer, last_seen_track_id='new')
        record = self._record()
        self.assertEqual(record.last_upload_at, newer)
        self.assertEqual(record.last_seen_track_id, 'new')


class AccountScheduleTest(unittest.TestCase):
    def setUp(self):
        self.store = InMemoryCheckStore()
        self.now = NOW
        # These cases are about the store and the clock, not about tiers. None of
        # their accounts has an upload date, so every one lands in the unknown
        # tier and gets account_cooldown -- the 3600 they were written against.
        self.timing = DownloaderTiming('soundcloud', {'account_cooldown': 3600})
        self.schedule = AccountSchedule('soundcloud', store=self.store, now=lambda: self.now)

    def test_all_accounts_are_due_on_a_fresh_install(self):
        self.assertEqual(self.schedule.due(['dj_a', 'dj_b'], self.timing), ['dj_a', 'dj_b'])

    def test_a_checked_account_drops_out_until_the_cooldown_passes(self):
        self.schedule.mark_checked('dj_a')
        self.assertEqual(self.schedule.due(['dj_a', 'dj_b'], self.timing), ['dj_b'])

    def test_the_account_returns_once_the_cooldown_has_passed(self):
        self.schedule.mark_checked('dj_a')
        self.now = NOW + timedelta(seconds=3601)
        self.assertEqual(self.schedule.due(['dj_a'], self.timing), ['dj_a'])

    def test_marking_the_same_account_twice_just_moves_the_timestamp(self):
        self.schedule.mark_checked('dj_a')
        self.now = NOW + timedelta(seconds=1800)
        self.schedule.mark_checked('dj_a')
        self.now = NOW + timedelta(seconds=3601)
        self.assertEqual(self.schedule.due(['dj_a'], self.timing), [])

    def test_sources_do_not_share_their_schedule(self):
        self.schedule.mark_checked('dj_a')
        other = AccountSchedule('youtube', store=self.store, now=lambda: self.now)
        self.assertEqual(other.due(['dj_a'], self.timing), ['dj_a'])


class AccountScheduleSurvivesStorageFailureTest(unittest.TestCase):
    def setUp(self):
        self.timing = DownloaderTiming('soundcloud', {'account_cooldown': 3600})

    class BrokenStore:
        def load(self, source):
            raise RuntimeError('database is down')

        def mark(self, source, account, when, last_upload_at=None, last_seen_track_id=None):
            raise RuntimeError('database is down')

    def test_everything_is_due_when_the_store_cannot_be_read(self):
        schedule = AccountSchedule('soundcloud', store=self.BrokenStore(), now=lambda: NOW)
        self.assertEqual(schedule.due(['dj_a'], self.timing), ['dj_a'])

    def test_marking_a_check_does_not_raise_when_the_store_is_down(self):
        schedule = AccountSchedule('soundcloud', store=self.BrokenStore(), now=lambda: NOW)
        schedule.mark_checked('dj_a')


class TieredDueTest(unittest.TestCase):
    """Each account waits out its own tier, not one cooldown shared by all."""

    def setUp(self):
        self.store = InMemoryCheckStore()
        self.now = NOW
        self.timing = DownloaderTiming('soundcloud', {})
        self.schedule = AccountSchedule('soundcloud', store=self.store, now=lambda: self.now)

    def _seen(self, account, upload_age_days, checked_ago_seconds):
        self.store.mark(
            'soundcloud',
            account,
            NOW - timedelta(seconds=checked_ago_seconds),
            last_upload_at=NOW - timedelta(days=upload_age_days),
            last_seen_track_id=f'{account}-track',
        )

    def test_a_fresh_account_is_due_once_its_own_cooldown_passes(self):
        self._seen('dj_fresh', upload_age_days=1, checked_ago_seconds=self.timing.account_cooldown + 1)
        self.assertEqual(self.schedule.due(['dj_fresh'], self.timing), ['dj_fresh'])

    def test_a_dormant_account_is_held_back_far_past_the_flat_cooldown(self):
        # Checked eight hours ago: due under the old flat six-hour cooldown,
        # nowhere near due on the dormant tier.
        self._seen('dj_dead', upload_age_days=800, checked_ago_seconds=8 * 3600)
        self.assertEqual(self.schedule.due(['dj_dead'], self.timing), [])

    def test_a_dormant_account_comes_back_after_its_own_cooldown(self):
        self._seen('dj_dead', upload_age_days=800, checked_ago_seconds=self.timing.dormant_cooldown + 1)
        self.assertEqual(self.schedule.due(['dj_dead'], self.timing), ['dj_dead'])

    def test_tiers_are_applied_per_account_in_one_pass(self):
        self._seen('dj_fresh', upload_age_days=1, checked_ago_seconds=8 * 3600)
        self._seen('dj_dead', upload_age_days=800, checked_ago_seconds=8 * 3600)
        self.assertEqual(self.schedule.due(['dj_fresh', 'dj_dead'], self.timing), ['dj_fresh'])

    def test_an_unprobed_account_is_due_on_the_fresh_cooldown(self):
        self.assertEqual(self.schedule.due(['dj_new'], self.timing), ['dj_new'])

    def test_an_account_that_uploaded_again_leaves_the_dormant_tier_at_once(self):
        self._seen('dj_back', upload_age_days=800, checked_ago_seconds=8 * 3600)
        self._seen('dj_back', upload_age_days=0, checked_ago_seconds=8 * 3600)
        self.assertEqual(self.schedule.due(['dj_back'], self.timing), ['dj_back'])

    def test_the_most_overdue_account_comes_first(self):
        # Alphabetical order meant the same tail of the list was always the part
        # that went unchecked when burst_size or a 403 cut a sweep short.
        self._seen('dj_a', upload_age_days=1, checked_ago_seconds=self.timing.account_cooldown + 60)
        self._seen('dj_z', upload_age_days=1, checked_ago_seconds=self.timing.account_cooldown + 9000)
        self.assertEqual(self.schedule.due(['dj_a', 'dj_z'], self.timing), ['dj_z', 'dj_a'])

    def test_an_account_that_was_never_checked_outranks_a_late_one(self):
        self._seen('dj_a', upload_age_days=1, checked_ago_seconds=self.timing.account_cooldown + 60)
        self.assertEqual(self.schedule.due(['dj_a', 'dj_new'], self.timing), ['dj_new', 'dj_a'])

    def test_ordering_does_not_let_an_undue_account_through(self):
        self._seen('dj_dead', upload_age_days=800, checked_ago_seconds=8 * 3600)
        self._seen('dj_a', upload_age_days=1, checked_ago_seconds=self.timing.account_cooldown + 60)
        self.assertEqual(self.schedule.due(['dj_dead', 'dj_a'], self.timing), ['dj_a'])

    def test_a_dormant_account_long_past_its_cooldown_outranks_a_barely_due_one(self):
        # Overdue-ness is measured against each account's own tier, so a dormant
        # account is not permanently last just for having a long cooldown.
        self._seen('dj_fresh', upload_age_days=1, checked_ago_seconds=self.timing.account_cooldown + 60)
        self._seen('dj_dead', upload_age_days=800, checked_ago_seconds=self.timing.dormant_cooldown + 90000)
        self.assertEqual(self.schedule.due(['dj_fresh', 'dj_dead'], self.timing), ['dj_dead', 'dj_fresh'])


class CooldownForTest(unittest.TestCase):
    """The ladder from 'when did this account last upload' to 'how long to wait'."""

    def setUp(self):
        self.timing = DownloaderTiming('soundcloud', {})

    def _for_age(self, days):
        return cooldown_for(NOW - timedelta(days=days), NOW, self.timing)

    def test_an_account_with_no_known_upload_is_checked_as_if_it_were_fresh(self):
        # A newly added account has no date yet and must not sink to the bottom
        # tier before a single probe has placed it.
        self.assertEqual(cooldown_for(None, NOW, self.timing), self.timing.account_cooldown)

    def test_an_upload_this_week_keeps_the_fastest_cooldown(self):
        self.assertEqual(self._for_age(3), self.timing.account_cooldown)

    def test_the_week_boundary_belongs_to_the_slower_tier(self):
        self.assertEqual(self._for_age(6.9), self.timing.account_cooldown)
        self.assertEqual(self._for_age(7), self.timing.recent_cooldown)

    def test_the_month_boundary(self):
        self.assertEqual(self._for_age(29.9), self.timing.recent_cooldown)
        self.assertEqual(self._for_age(30), self.timing.monthly_cooldown)

    def test_the_quarter_boundary(self):
        self.assertEqual(self._for_age(89.9), self.timing.monthly_cooldown)
        self.assertEqual(self._for_age(90), self.timing.occasional_cooldown)

    def test_the_year_boundary(self):
        self.assertEqual(self._for_age(364.9), self.timing.occasional_cooldown)
        self.assertEqual(self._for_age(365), self.timing.dormant_cooldown)

    def test_a_long_dead_account_stays_on_the_dormant_cooldown(self):
        self.assertEqual(self._for_age(4000), self.timing.dormant_cooldown)

    def test_an_upload_stamped_in_the_future_counts_as_fresh(self):
        self.assertEqual(self._for_age(-5), self.timing.account_cooldown)

    def test_the_backoff_multiplier_stretches_whichever_tier_applies(self):
        stretched = DownloaderTiming('soundcloud', {}, multiplier=4)
        self.assertEqual(cooldown_for(NOW - timedelta(days=800), NOW, stretched), self.timing.dormant_cooldown * 4)


if __name__ == '__main__':
    unittest.main()


class DeepSweepDueTest(unittest.TestCase):
    def setUp(self):
        self.now = NOW
        self.store = InMemoryCheckStore()
        self.schedule = AccountSchedule('soundcloud', store=self.store, now=lambda: self.now)

    def test_an_account_never_deep_swept_is_due(self):
        self.assertTrue(self.schedule.deep_due('dj_a', 30))

    def test_an_account_that_was_checked_but_never_deep_swept_is_due(self):
        self.schedule.mark_checked('dj_a')
        self.assertTrue(self.schedule.deep_due('dj_a', 30))

    def test_an_account_deep_swept_yesterday_is_not_due(self):
        self.schedule.mark_deep_swept('dj_a', when=self.now - timedelta(days=1))
        self.assertFalse(self.schedule.deep_due('dj_a', 30))

    def test_an_account_deep_swept_long_enough_ago_is_due_again(self):
        self.schedule.mark_deep_swept('dj_a', when=self.now - timedelta(days=31))
        self.assertTrue(self.schedule.deep_due('dj_a', 30))

    def test_zero_days_turns_the_deep_sweep_off(self):
        self.assertFalse(self.schedule.deep_due('dj_a', 0))

    def test_marking_a_deep_sweep_leaves_the_ordinary_check_alone(self):
        self.schedule.mark_checked('dj_a', when=self.now - timedelta(hours=2), last_seen_track_id='t9')
        self.schedule.mark_deep_swept('dj_a')
        record = self.store.load('soundcloud')['dj_a']
        self.assertEqual('t9', record.last_seen_track_id)
        self.assertEqual(self.now - timedelta(hours=2), record.last_checked_at)
        self.assertEqual(self.now, record.last_deep_sweep_at)

    def test_an_ordinary_check_leaves_the_deep_sweep_date_alone(self):
        self.schedule.mark_deep_swept('dj_a', when=self.now - timedelta(days=2))
        self.schedule.mark_checked('dj_a')
        record = self.store.load('soundcloud')['dj_a']
        self.assertEqual(self.now - timedelta(days=2), record.last_deep_sweep_at)

    def test_a_broken_store_leaves_the_account_due_rather_than_stuck(self):
        class BrokenStore:
            def load(self, source):
                raise RuntimeError('database is down')

            def mark_deep(self, *args):
                raise RuntimeError('database is down')

        schedule = AccountSchedule('soundcloud', store=BrokenStore(), now=lambda: self.now)
        schedule.mark_deep_swept('dj_a')
        self.assertTrue(schedule.deep_due('dj_a', 30))
