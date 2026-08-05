import unittest
from unittest.mock import patch

from services.common.step import Step


class StepShouldRunTest(unittest.TestCase):

    def test_a_step_without_conditions_always_runs(self):
        step = Step('tagger', lambda: None)

        self.assertTrue(step.should_run(set()))
        self.assertTrue(step.should_run({'anything'}))

    def test_a_conditional_step_runs_when_one_of_its_keys_is_requested(self):
        step = Step('tagger', lambda: None, condition_keys=['tag', 'retag'])

        self.assertTrue(step.should_run({'retag'}))

    def test_a_conditional_step_is_skipped_for_other_keys(self):
        step = Step('tagger', lambda: None, condition_keys=['tag'])

        self.assertFalse(step.should_run({'scan'}))

    def test_all_runs_every_conditional_step(self):
        step = Step('tagger', lambda: None, condition_keys=['tag'])

        self.assertTrue(step.should_run({'all'}))

    def test_an_empty_condition_list_is_not_the_same_as_no_conditions(self):
        step = Step('tagger', lambda: None, condition_keys=[])

        self.assertFalse(step.should_run({'tag'}))
        self.assertTrue(step.should_run({'all'}))


class StepRunTest(unittest.TestCase):

    def setUp(self):
        patcher = patch('services.common.step.job_manager')
        self.addCleanup(patcher.stop)
        self.job_manager = patcher.start()
        self.job_manager.register.return_value = 'job-1'

    def test_a_skipped_step_registers_no_job(self):
        called = []
        step = Step('tagger', lambda: called.append(True), condition_keys=['tag'])

        self.assertIsNone(step.run({'scan'}))
        self.assertEqual(called, [])
        self.job_manager.register.assert_not_called()

    def test_an_action_without_parameters_is_called_bare(self):
        called = []
        step = Step('tagger', lambda: called.append('bare'))

        job_id = step.run({'all'}, extra='ignored')

        self.assertEqual(job_id, 'job-1')
        self.assertEqual(called, ['bare'])
        self.job_manager.update.assert_called_once_with('job-1', 'completed')

    def test_an_action_that_takes_steps_receives_them_positionally(self):
        seen = {}

        def action(steps, limit=None):
            seen['steps'] = steps
            seen['limit'] = limit

        Step('tagger', action).run({'all'}, limit=5)

        self.assertEqual(seen, {'steps': {'all'}, 'limit': 5})

    def test_an_action_with_other_parameters_receives_only_the_keywords(self):
        seen = {}

        def action(limit=None):
            seen['limit'] = limit

        Step('tagger', action).run({'all'}, limit=5)

        self.assertEqual(seen, {'limit': 5})

    def test_a_failing_action_marks_the_job_failed_without_raising(self):
        def action():
            raise RuntimeError('boom')

        job_id = Step('tagger', action).run({'all'})

        self.assertEqual(job_id, 'job-1')
        self.job_manager.update.assert_called_once_with('job-1', 'failed', 'boom')


if __name__ == '__main__':
    unittest.main()
