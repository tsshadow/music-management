import uuid
from threading import Lock

class JobManager:
    """Simple in-memory registry for tracking job status."""
    def __init__(self):
        self.jobs = {}
        self.lock = Lock()

    def register(self, step_name):
        job_id = str(uuid.uuid4())
        with self.lock:
            self.jobs[job_id] = {"step": step_name, "status": "running"}
        return job_id

    def update(self, job_id, status, error=None):
        with self.lock:
            job = self.jobs.get(job_id)
            if job:
                job["status"] = status
                if error:
                    job["error"] = error

    def list_active(self):
        with self.lock:
            return [
                {"job_id": job_id, "step": data["step"]}
                for job_id, data in self.jobs.items()
                if data.get("status") == "running"
            ]

    def get(self, job_id):
        with self.lock:
            return self.jobs.get(job_id)

job_manager = JobManager()
