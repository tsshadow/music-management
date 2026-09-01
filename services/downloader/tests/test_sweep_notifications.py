"""A 403 has to reach the phone, because it means downloads have stopped.

A 429 is routine self-regulation; a 403 is the service refusing us outright, and
the wait doubles up with every repeat until it hits the cap. The notification is
therefore sent whenever the wait actually grows, and stays quiet once the ladder
has plateaued so a parked source cannot spam the topic forever.
"""

import unittest
from datetime import datetime

from services.downloader.account_schedule import AccountSchedule, InMemoryCheckStore
from services.downloader.rate_state import InMemoryRateStateStore, RateState
from services.downloader.sweep import SweepPolicy, format_wait
from services.downloader.timing import load_timing

NOW = datetime(2026, 8, 3, 12, 0, 0)


class RecordingNotifier:
    """Stands in for the ntfy service and remembers what it was asked to send."""

    def __init__(self):
        self.sent = []

    def notify(self, message, title='Music Management'):
        self.sent.append((title, message))
        return True


class ExplodingNotifier:
    def notify(self, message, title='Music Management'):
        raise RuntimeError('ntfy is down')


def build_policy(notifier, overrides=None, source='soundcloud'):
    timing = load_timing(source, overrides=overrides or {})
    rate_state = RateState(source, timing, store=InMemoryRateStateStore(), now=lambda: NOW, jitter=lambda: 1.0)
    schedule = AccountSchedule(source, store=InMemoryCheckStore())
    return SweepPolicy(source, timing=timing, rate_state=rate_state, schedule=schedule, notifier=notifier)


class TestFormatWait(unittest.TestCase):
    def test_seconds_stay_seconds(self):
        self.assertEqual(format_wait(45), '45 sec')

    def test_minutes_are_rounded(self):
        self.assertEqual(format_wait(240), '4 min')

    def test_hours_keep_one_decimal_when_it_matters(self):
        self.assertEqual(format_wait(5400), '1,5 uur')

    def test_a_whole_hour_drops_the_decimal(self):
        self.assertEqual(format_wait(3600), '1 uur')


class TestNotifyOn403(unittest.TestCase):
    def test_the_first_403_is_announced(self):
        notifier = RecordingNotifier()
        build_policy(notifier).park('403', 'monstercat')

        self.assertEqual(len(notifier.sent), 1)

    def test_the_notification_names_the_source_and_the_account(self):
        notifier = RecordingNotifier()
        build_policy(notifier).park('403', 'monstercat')

        title, message = notifier.sent[0]
        self.assertIn('403', title)
        self.assertIn('soundcloud', message)
        self.assertIn('monstercat', message)

    def test_the_notification_reports_the_new_wait(self):
        notifier = RecordingNotifier()
        # backoff_403_base for soundcloud is 240 seconds.
        build_policy(notifier).park('403', 'monstercat')

        self.assertIn('4 min', notifier.sent[0][1])

    def test_a_repeat_403_is_announced_again_because_the_wait_grew(self):
        notifier = RecordingNotifier()
        policy = build_policy(notifier)

        policy.park('403', 'monstercat')
        policy.park('403', 'monstercat')

        self.assertEqual(len(notifier.sent), 2)

    def test_the_repeat_notification_reports_the_growth(self):
        notifier = RecordingNotifier()
        policy = build_policy(notifier)

        policy.park('403', 'monstercat')
        policy.park('403', 'monstercat')

        # 240 seconds, then 240 * 4.
        self.assertIn('4 min', notifier.sent[1][1])
        self.assertIn('16 min', notifier.sent[1][1])

    def test_a_capped_ladder_stops_notifying(self):
        notifier = RecordingNotifier()
        # A cap equal to the base means the wait can never grow.
        policy = build_policy(notifier, overrides={'backoff_403_base': 240, 'backoff_403_cap': 240})

        policy.park('403', 'monstercat')
        policy.park('403', 'monstercat')
        policy.park('403', 'monstercat')

        self.assertEqual(len(notifier.sent), 1)

    def test_a_429_is_not_announced(self):
        notifier = RecordingNotifier()
        build_policy(notifier).park('429', 'monstercat')

        self.assertEqual(notifier.sent, [])

    def test_a_403_after_a_clean_run_is_announced_again(self):
        notifier = RecordingNotifier()
        policy = build_policy(notifier)

        policy.park('403', 'monstercat')
        policy.rate_state.record_success()
        policy.park('403', 'monstercat')

        self.assertEqual(len(notifier.sent), 2)

    def test_a_broken_notifier_does_not_stop_the_backoff(self):
        policy = build_policy(ExplodingNotifier())

        limited = policy.park('403', 'monstercat')

        self.assertEqual(limited.wait, 240)
        self.assertEqual(policy.rate_state.cooldown_remaining(), 240)


if __name__ == '__main__':
    unittest.main()
