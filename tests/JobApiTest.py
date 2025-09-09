import time
import threading
import unittest
import importlib
import sys

# Ensure the real requests module is available (FileRepairTest stubs it)
sys.modules.pop('requests', None)
requests = importlib.import_module('requests')
from step import Step
from api import start_api_server
from job_manager import job_manager


class JobApiTest(unittest.TestCase):
    def test_job_lifecycle_and_api(self):
        job_manager.jobs.clear()
        # start API server on random port
        server = start_api_server(port=0)
        try:
            host, port = server.server_address
            base = f"http://{host}:{port}"

            def action():
                time.sleep(0.2)

            step = Step("Example", ["test"], action)

            t = threading.Thread(target=lambda: step.run(["test"]))
            t.start()
            time.sleep(0.05)  # allow job to register

            resp = requests.get(f"{base}/jobs")
            self.assertEqual(resp.status_code, 200)
            jobs = resp.json()
            self.assertEqual(len(jobs), 1)
            job_id = jobs[0]["job_id"]
            self.assertEqual(jobs[0]["step"], "Example")

            t.join()

            status_resp = requests.get(f"{base}/status", params={"job_id": job_id})
            self.assertEqual(status_resp.status_code, 200)
            status = status_resp.json()
            self.assertEqual(status["status"], "completed")
            self.assertEqual(status["step"], "Example")
        finally:
            server.shutdown()
            server.server_close()

    def test_failed_job_status(self):
        job_manager.jobs.clear()
        server = start_api_server(port=0)
        try:
            host, port = server.server_address
            base = f"http://{host}:{port}"

            def failing_action():
                raise RuntimeError("boom")

            step = Step("FailStep", ["test"], failing_action)

            result = []
            t = threading.Thread(target=lambda: result.append(step.run(["test"])))
            t.start()
            t.join()
            job_id = result[0]

            status = requests.get(f"{base}/status", params={"job_id": job_id}).json()
            self.assertEqual(status["status"], "failed")
            self.assertEqual(status["step"], "FailStep")
            self.assertIn("error", status)
        finally:
            server.shutdown()
            server.server_close()

if __name__ == "__main__":
    unittest.main()
