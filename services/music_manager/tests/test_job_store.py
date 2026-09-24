"""The curation pages' in-process job state (services/music_manager/job_store.py)."""

import unittest

from services.music_manager.job_store import JobStore


class JobStoreTest(unittest.TestCase):
    def test_a_running_job_is_read_from_its_live_state(self):
        store = JobStore()
        store.jobs['a'] = {'status': 'running'}
        self.assertEqual(store.state('a'), {'status': 'running'})

    def test_a_finished_job_keeps_a_copy_of_its_final_state(self):
        store = JobStore()
        live = {'status': 'finished', 'progress': 3}
        store.finish('a', live)
        live['progress'] = 99
        self.assertEqual(store.results['a'], {'status': 'finished', 'progress': 3})
        self.assertEqual(list(store.history), ['a'])

    def test_an_unknown_job_has_no_state(self):
        self.assertIsNone(JobStore().state('nope'))

    def test_finishing_twice_keeps_one_history_entry(self):
        store = JobStore()
        store.finish('a', {'status': 'failed'})
        store.finish('a', {'status': 'finished'})
        self.assertEqual(list(store.history), ['a'])
        self.assertEqual(store.results['a'], {'status': 'finished'})

    def test_only_the_newest_finished_jobs_are_kept(self):
        """The registry this replaced never dropped anything, for the life of the process."""
        store = JobStore(keep_finished=2)
        for job_id in ('a', 'b', 'c'):
            store.jobs[job_id] = {'status': 'finished'}
            store.finish(job_id, store.jobs[job_id])
        self.assertEqual(list(store.history), ['c', 'b'])
        self.assertNotIn('a', store.results)
        self.assertNotIn('a', store.jobs)
        self.assertIsNone(store.state('a'))

    def test_a_running_job_is_never_evicted(self):
        store = JobStore(keep_finished=1)
        store.jobs['running'] = {'status': 'running'}
        store.finish('a', {'status': 'finished'})
        store.finish('b', {'status': 'finished'})
        self.assertIn('running', store.jobs)


if __name__ == '__main__':
    unittest.main()
