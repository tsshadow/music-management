import uuid
import os
import requests
import logging
from threading import Lock
from typing import Dict, Any, List, Optional

class JobManager:
    """Simple in-memory registry for tracking job status, with optional remote push."""

    def __init__(self):
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self.lock = Lock()
        # HUB_API_URL should be like http://music-manager:8000/jobs
        self.hub_url = os.getenv('HUB_API_URL')
        self.api_key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY')

    def register(self, step_name: str) -> str:
        job_id = str(uuid.uuid4())
        job_data = {'step': step_name, 'status': 'running'}
        with self.lock:
            self.jobs[job_id] = job_data
        self._push(job_id, job_data)
        return job_id

    def update(self, job_id: str, status: str, error: Optional[str] = None):
        with self.lock:
            job = self.jobs.get(job_id)
            if job:
                job['status'] = status
                if error:
                    job['error'] = error
                self._push(job_id, job)

    def _push(self, job_id: str, job_data: Dict[str, Any]):
        if not self.hub_url:
            return
        try:
            url = f"{self.hub_url.rstrip('/')}/register/{job_id}"
            requests.post(
                url,
                json=job_data,
                headers={"X-API-KEY": self.api_key},
                timeout=2
            )
        except Exception as e:
            logging.debug(f"Failed to push job status to hub: {e}")

    def list_active(self) -> List[Dict[str, Any]]:
        with self.lock:
            return [{'job_id': job_id, 'step': data['step']} for job_id, data in self.jobs.items() if data.get('status') == 'running']

    def get(self, job_id: str) -> Optional[Dict[str, Any]]:
        with self.lock:
            return self.jobs.get(job_id)

job_manager = JobManager()
