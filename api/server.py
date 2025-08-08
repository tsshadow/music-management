import logging
import uuid
from typing import Dict

from fastapi import FastAPI, BackgroundTasks, HTTPException

from .steps import step_map

app = FastAPI()

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    force=True,
)

jobs: Dict[str, Dict] = {}


@app.get("/api/steps")
def list_steps():
    """Return available step keys for dropdowns."""
    return {"steps": sorted(step_map.keys())}


@app.get("/api/jobs")
def list_jobs():
    """Return currently active jobs for selection."""
    return {
        "jobs": [
            job
            for job in jobs.values()
            if job["status"] in {"queued", "running"}
        ]
    }


class JobLogHandler(logging.Handler):
    def __init__(self, job_id: str):
        super().__init__()
        self.job_id = job_id

    def emit(self, record: logging.LogRecord) -> None:
        jobs[self.job_id]["log"].append(self.format(record))


def execute_step(step_name: str, job_id: str):
    job = jobs[job_id]
    step = step_map.get(step_name)
    if not step:
        job["status"] = "error"
        job["log"].append(f"Unknown step: {step_name}")
        return

    handler = JobLogHandler(job_id)
    handler.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
    logging.getLogger().addHandler(handler)

    try:
        job["status"] = "running"
        step.run({step_name})
        job["status"] = "done"
    except Exception as e:  # pragma: no cover - for robustness
        job["status"] = "error"
        job["log"].append(str(e))
    finally:
        logging.getLogger().removeHandler(handler)


@app.post("/api/run/{step_name}")
def run_step_endpoint(step_name: str, background_tasks: BackgroundTasks):
    if step_name not in step_map:
        raise HTTPException(status_code=404, detail="Unknown step")

    job_id = str(uuid.uuid4())
    jobs[job_id] = {"id": job_id, "step": step_name, "status": "queued", "log": []}
    background_tasks.add_task(execute_step, step_name, job_id)
    return jobs[job_id]


@app.get("/api/job/{job_id}")
def get_job(job_id: str):
    job = jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job
