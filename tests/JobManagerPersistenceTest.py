import tempfile
import unittest
from pathlib import Path

from job_manager import JobManager


class JobManagerPersistenceTest(unittest.TestCase):
    def test_persists_jobs_across_instances(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / "jobs.json"

            manager = JobManager(storage_path=storage, register_atexit=False)
            job_id = manager.register("Example")
            manager.update(job_id, "completed")

            reloaded = JobManager(storage_path=storage, register_atexit=False)
            job = reloaded.get(job_id)

            self.assertIsNotNone(job)
            self.assertEqual(job["status"], "completed")
            self.assertEqual(job["step"], "Example")

    def test_running_jobs_marked_interrupted_on_load(self) -> None:
        with tempfile.TemporaryDirectory() as tmpdir:
            storage = Path(tmpdir) / "jobs.json"

            manager = JobManager(storage_path=storage, register_atexit=False)
            job_id = manager.register("Example")
            # simulate abrupt shutdown without updating status
            del manager

            reloaded = JobManager(storage_path=storage, register_atexit=False)
            job = reloaded.get(job_id)

            self.assertIsNotNone(job)
            self.assertEqual(job["status"], "interrupted")


if __name__ == "__main__":
    unittest.main()
