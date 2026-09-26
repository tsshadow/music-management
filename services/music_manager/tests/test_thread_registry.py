"""run_forever: the one place every background loop gets its resilience and heartbeat from."""

import threading
import unittest
from unittest.mock import patch

from services.music_manager import thread_registry
from services.tests.stop_after import StopAfter


class _Stop(BaseException):
    """Escapes run_forever in a test; a BaseException, since run_forever only catches Exception."""


class RunForeverTest(unittest.TestCase):
    def setUp(self):
        thread_registry.reset()
        self.addCleanup(thread_registry.reset)

    def _run(self, tick, interval, sleeps, **kwargs):
        """Run the loop until its `sleeps`-th pause; returns the delays it asked to wait."""
        stop = StopAfter(sleeps)
        thread_registry.run_forever('probe', tick, interval, stop=stop, **kwargs)
        return stop.delays

    def test_a_tick_that_raises_keeps_the_loop_running_and_logs_it(self):
        calls = []

        def tick():
            calls.append(1)
            if len(calls) == 1:
                raise RuntimeError('MariaDB restarting')

        with self.assertLogs('music-manager.threads', 'ERROR') as logs:
            delays = self._run(tick, 300, sleeps=2)

        self.assertEqual(len(calls), 2)
        self.assertIn('MariaDB restarting', '\n'.join(logs.output))
        # logger.exception: the traceback travels along into the events pipeline.
        self.assertIn('Traceback', '\n'.join(logs.output))
        self.assertEqual(delays, [10.0, 300])

    def test_backoff_doubles_up_to_the_interval_and_resets_after_a_success(self):
        outcomes = iter([RuntimeError, RuntimeError, RuntimeError, RuntimeError, None, RuntimeError])

        def tick():
            outcome = next(outcomes)
            if outcome is not None:
                raise outcome('down')

        with self.assertLogs('music-manager.threads', 'ERROR'):
            delays = self._run(tick, 60, sleeps=6)

        self.assertEqual(delays, [10.0, 20.0, 40.0, 60, 60, 10.0])

    def test_without_backoff_a_failure_waits_the_normal_interval(self):
        def tick():
            raise RuntimeError('locked')

        with self.assertLogs('music-manager.threads', 'ERROR'):
            delays = self._run(tick, 3600, sleeps=2, backoff=False)

        self.assertEqual(delays, [3600, 3600])

    def test_a_tick_can_choose_its_next_sleep(self):
        answers = iter([60, None, 0])
        delays = self._run(lambda: next(answers), 300, sleeps=3)
        self.assertEqual(delays, [60, 300, 0])

    def test_keyboard_interrupt_is_not_swallowed(self):
        def tick():
            raise KeyboardInterrupt

        with self.assertRaises(KeyboardInterrupt):
            thread_registry.run_forever('probe', tick, 1, stop=StopAfter(1))

    def test_the_pause_never_goes_through_time_sleep(self):
        """Bug report 099: a finite side_effect on the shared `time.sleep` ran dry mid-test.

        Without a `stop` event the loop still pauses on an event of its own, so patching
        `time.sleep` elsewhere in the process can no longer reach it.
        """
        calls = []

        def tick():
            calls.append(1)
            if len(calls) == 2:
                raise _Stop

        with (
            patch('time.sleep', side_effect=AssertionError('run_forever used time.sleep')) as sleep,
            self.assertRaises(_Stop),
        ):
            thread_registry.run_forever('probe', tick, 0.01)
        sleep.assert_not_called()
        self.assertEqual(len(calls), 2)

    def test_only_a_completed_tick_moves_the_heartbeat(self):
        outcomes = iter([None, RuntimeError('down')])

        def tick():
            outcome = next(outcomes)
            if outcome is not None:
                raise outcome

        with self.assertLogs('music-manager.threads', 'ERROR'):
            self._run(tick, 300, sleeps=2)

        heartbeat = thread_registry._heartbeats['probe']
        self.assertEqual(heartbeat.ticks, 1)
        self.assertEqual(heartbeat.failures, 1)

    def test_default_staleness_is_three_rounds_but_at_least_an_hour(self):
        self.assertEqual(thread_registry.default_stale_after(5), 3600)
        self.assertEqual(thread_registry.default_stale_after(3600), 3 * 3600)
        self.assertEqual(thread_registry.default_stale_after(86400), 3 * 86400)


class HeartbeatStatusTest(unittest.TestCase):
    def setUp(self):
        thread_registry.reset()
        self.addCleanup(thread_registry.reset)

    def test_a_stale_heartbeat_marks_a_living_thread_unhealthy(self):
        stop = threading.Event()
        self.addCleanup(stop.set)
        thread_registry.start_thread('radio', stop.wait)
        thread_registry.register_heartbeat('radio', stale_after=60)
        self.assertTrue(thread_registry.thread_status()['radio'])

        thread_registry._heartbeats['radio'].last_beat_monotonic -= 61

        self.assertFalse(thread_registry.thread_status()['radio'])
        detail = thread_registry.thread_heartbeats()['radio']
        self.assertTrue(detail['alive'])
        self.assertTrue(detail['stale'])

    def test_a_thread_without_heartbeat_is_judged_on_liveness(self):
        stop = threading.Event()
        self.addCleanup(stop.set)
        thread_registry.start_thread('plain', stop.wait)

        self.assertTrue(thread_registry.thread_status()['plain'])
        self.assertIsNone(thread_registry.thread_heartbeats()['plain']['last_tick_age_seconds'])


if __name__ == '__main__':
    unittest.main()
