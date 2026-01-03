import time
import threading
import unittest
import requests
from services.common.api.step import Step
from services.common.api import start_api_server
from services.common.api.job_manager import job_manager

class JobApiTest(unittest.TestCase):

    def test_job_lifecycle_and_api(self):
        job_manager.jobs.clear()
        server = start_api_server(port=0)
        time.sleep(0.1)
        try:
            host, port = server.server_address
            base = f'http://{host}:{port}'

            def action(steps=None):
                time.sleep(0.2)
            step = Step('Example', action, condition_keys=['test'])
            t = threading.Thread(target=lambda: step.run(['test']))
            t.start()
            time.sleep(0.05)
            resp = requests.get(f'{base}/jobs')
            self.assertEqual(resp.status_code, 200)
            jobs = resp.json()
            self.assertEqual(len(jobs), 1)
            job_id = jobs[0]['job_id']
            self.assertEqual(jobs[0]['step'], 'Example')
            t.join()
            status_resp = requests.get(f'{base}/status', params={'job_id': job_id})
            self.assertEqual(status_resp.status_code, 200)
            status = status_resp.json()
            self.assertEqual(status['status'], 'completed')
            self.assertEqual(status['step'], 'Example')
        finally:
            server.shutdown()
            server.server_close()

    def test_failed_job_status(self):
        job_manager.jobs.clear()
        server = start_api_server(port=0)
        time.sleep(0.1)
        try:
            host, port = server.server_address
            base = f'http://{host}:{port}'

            def failing_action(steps=None):
                raise RuntimeError('boom')
            step = Step('FailStep', failing_action, condition_keys=['test'])
            result = []
            t = threading.Thread(target=lambda: result.append(step.run(['test'])))
            t.start()
            t.join()
            job_id = result[0]
            status = requests.get(f'{base}/status', params={'job_id': job_id}).json()
            self.assertEqual(status['status'], 'failed')
            self.assertEqual(status['step'], 'FailStep')
            self.assertIn('error', status)
        finally:
            server.shutdown()
            server.server_close()
if __name__ == '__main__':
    unittest.main()