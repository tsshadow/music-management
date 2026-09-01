"""Coverage for services/tagger/deep_run.py: the cadence, its off switch and its bounds."""

import unittest
from unittest.mock import MagicMock

from services.tagger import deep_run as deep_run_module


class DeepRunTestCase(unittest.TestCase):
    def setUp(self):
        self.helper = MagicMock()
        self.helper.mark_stale_for_rescan.return_value = 0
        self.helper.count_stale.return_value = 0
        self.values = {'tagger_deep_run_days': 30, 'tagger_deep_run_batch': 200}
        self.settings = MagicMock()
        self.settings.get.side_effect = lambda key, default=None: self.values.get(key, default)

    def tick(self):
        return deep_run_module.deep_run_tick(helper=self.helper, settings=self.settings)


class CadenceTest(DeepRunTestCase):
    def test_the_configured_window_and_batch_reach_the_helper(self):
        self.helper.mark_stale_for_rescan.return_value = 200
        self.assertEqual(self.tick(), 200)
        self.helper.mark_stale_for_rescan.assert_called_once_with(30, 200)

    def test_a_window_of_zero_is_the_off_switch(self):
        self.values['tagger_deep_run_days'] = 0
        self.assertEqual(self.tick(), 0)
        self.helper.mark_stale_for_rescan.assert_not_called()

    def test_a_batch_of_zero_queues_nothing(self):
        self.values['tagger_deep_run_batch'] = 0
        self.assertEqual(self.tick(), 0)
        self.helper.mark_stale_for_rescan.assert_not_called()

    def test_a_missing_setting_falls_back_to_the_off_switch(self):
        self.values['tagger_deep_run_days'] = None
        self.assertEqual(self.tick(), 0)
        self.helper.mark_stale_for_rescan.assert_not_called()

    def test_a_negative_setting_is_refused_rather_than_inverted(self):
        self.values['tagger_deep_run_batch'] = -5
        self.assertEqual(self.tick(), 0)
        self.helper.mark_stale_for_rescan.assert_not_called()

    def test_the_remaining_backlog_is_only_counted_when_something_was_queued(self):
        self.tick()
        self.helper.count_stale.assert_not_called()
        self.helper.mark_stale_for_rescan.return_value = 5
        self.tick()
        self.helper.count_stale.assert_called_once_with(30)

    def test_a_database_failure_never_reaches_the_tagging_round(self):
        self.helper.mark_stale_for_rescan.side_effect = RuntimeError('database gone')
        self.assertEqual(self.tick(), 0)

    def test_a_failure_while_counting_the_backlog_is_swallowed_too(self):
        self.helper.mark_stale_for_rescan.return_value = 5
        self.helper.count_stale.side_effect = RuntimeError('database gone')
        self.assertEqual(self.tick(), 5)


if __name__ == '__main__':
    unittest.main()
