import unittest
from unittest.mock import patch

from services.common.job_manager import JobManager


class JobManagerRegistryTest(unittest.TestCase):
    """Covers the in-memory registry with the hub push disabled (no HUB_API_URL)."""

    def setUp(self):
        with patch.dict('os.environ', {}, clear=True):
            self.manager = JobManager()

    def test_register_returns_a_unique_running_job(self):
        first = self.manager.register('tagger')
        second = self.manager.register('tagger')

        self.assertNotEqual(first, second)
        self.assertEqual(self.manager.get(first), {'step': 'tagger', 'status': 'running'})

    def test_update_sets_the_status(self):
        job_id = self.manager.register('tagger')

        self.manager.update(job_id, 'completed')

        self.assertEqual(self.manager.get(job_id)['status'], 'completed')
        self.assertNotIn('error', self.manager.get(job_id))

    def test_update_records_an_error_message(self):
        job_id = self.manager.register('tagger')

        self.manager.update(job_id, 'failed', 'boom')

        self.assertEqual(self.manager.get(job_id), {'step': 'tagger', 'status': 'failed', 'error': 'boom'})

    def test_update_ignores_an_unknown_job(self):
        self.manager.update('does-not-exist', 'completed')

        self.assertIsNone(self.manager.get('does-not-exist'))

    def test_list_active_only_returns_running_jobs(self):
        running = self.manager.register('tagger')
        done = self.manager.register('scanner')
        self.manager.update(done, 'completed')

        self.assertEqual(self.manager.list_active(), [{'job_id': running, 'step': 'tagger'}])

    def test_get_returns_none_for_an_unknown_job(self):
        self.assertIsNone(self.manager.get('does-not-exist'))


class JobManagerPushTest(unittest.TestCase):
    def _manager(self, **env):
        with patch.dict('os.environ', env, clear=True):
            return JobManager()

    def test_nothing_is_pushed_without_a_hub_url(self):
        manager = self._manager()

        with patch('services.common.job_manager.requests.post') as post:
            manager.register('tagger')

        post.assert_not_called()

    def test_register_pushes_the_job_to_the_hub(self):
        manager = self._manager(HUB_API_URL='http://music-manager:8000/jobs/', API_KEY='secret')

        with patch('services.common.job_manager.requests.post') as post:
            job_id = manager.register('tagger')

        post.assert_called_once_with(
            f'http://music-manager:8000/jobs/register/{job_id}',
            json={'step': 'tagger', 'status': 'running'},
            headers={'X-API-KEY': 'secret'},
            timeout=2,
        )

    def test_the_api_key_falls_back_to_muma_api_key(self):
        manager = self._manager(HUB_API_URL='http://hub/jobs', MUMA_API_KEY='fallback')

        with patch('services.common.job_manager.requests.post') as post:
            manager.register('tagger')

        self.assertEqual(post.call_args.kwargs['headers'], {'X-API-KEY': 'fallback'})

    def test_publish_sends_an_ad_hoc_payload_for_a_job(self):
        manager = self._manager(HUB_API_URL='http://hub/jobs')

        with patch('services.common.job_manager.requests.post') as post:
            manager.publish({'progress': 50}, 'job-1')

        self.assertEqual(post.call_args[0][0], 'http://hub/jobs/register/job-1')
        self.assertEqual(post.call_args.kwargs['json'], {'progress': 50})

    def test_publish_without_a_job_id_uses_the_global_channel(self):
        manager = self._manager(HUB_API_URL='http://hub/jobs')

        with patch('services.common.job_manager.requests.post') as post:
            manager.publish({'progress': 50})

        self.assertEqual(post.call_args[0][0], 'http://hub/jobs/register/global')

    def test_a_failing_hub_never_breaks_the_caller(self):
        manager = self._manager(HUB_API_URL='http://hub/jobs')

        with patch('services.common.job_manager.requests.post', side_effect=Exception('unreachable')):
            job_id = manager.register('tagger')

        self.assertEqual(manager.get(job_id)['status'], 'running')


if __name__ == '__main__':
    unittest.main()
