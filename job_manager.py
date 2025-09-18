from __future__ import annotations

import atexit
import json
import logging
import os
import uuid
from pathlib import Path
from threading import Lock
from typing import Any, Dict


LOGGER = logging.getLogger(__name__)


def _default_storage_path() -> Path:
    """Determine the default location for persisted job state."""

    env_path = os.environ.get("JOB_MANAGER_STORAGE")
    if env_path:
        return Path(env_path).expanduser().resolve()
    return Path(__file__).with_name("jobs_state.json")


class JobManager:
    """Simple in-memory registry for tracking job status."""

    def __init__(self, storage_path: str | os.PathLike[str] | None = None, register_atexit: bool = True):
        self.lock = Lock()
        self.storage_path = Path(storage_path) if storage_path else _default_storage_path()
        self.jobs: Dict[str, Dict[str, Any]] = {}
        self._load()
        if register_atexit:
            atexit.register(self._persist)

    def register(self, step_name: str) -> str:
        job_id = str(uuid.uuid4())
        with self.lock:
            self.jobs[job_id] = {"step": step_name, "status": "running"}
            self._persist_locked()
        return job_id

    def update(self, job_id: str, status: str, error: str | None = None) -> None:
        with self.lock:
            job = self.jobs.get(job_id)
            if job:
                job["status"] = status
                if error:
                    job["error"] = error
                else:
                    job.pop("error", None)
                self._persist_locked()

    def list_active(self) -> list[dict[str, str]]:
        with self.lock:
            return [
                {"job_id": job_id, "step": data["step"]}
                for job_id, data in self.jobs.items()
                if data.get("status") == "running"
            ]

    def get(self, job_id: str) -> Dict[str, Any] | None:
        with self.lock:
            return self.jobs.get(job_id)

    def clear(self) -> None:
        """Clear all jobs from memory and remove any persisted state."""

        with self.lock:
            self.jobs.clear()
            try:
                if self.storage_path.exists():
                    self.storage_path.unlink()
            except OSError as exc:  # pragma: no cover - failure is non-critical
                LOGGER.warning("Failed to remove job state file %s: %s", self.storage_path, exc)

    def _persist(self) -> None:
        with self.lock:
            self._persist_locked()

    def _persist_locked(self) -> None:
        """Persist job state to disk. Caller must hold ``self.lock``."""

        try:
            if not self.jobs:
                if self.storage_path.exists():
                    self.storage_path.unlink()
                return

            self.storage_path.parent.mkdir(parents=True, exist_ok=True)
            with self.storage_path.open("w", encoding="utf-8") as handle:
                json.dump(self.jobs, handle)
        except OSError as exc:  # pragma: no cover - failure is non-critical
            LOGGER.warning("Failed to persist job state to %s: %s", self.storage_path, exc)

    def _load(self) -> None:
        """Load previously persisted job state."""

        if not self.storage_path.exists():
            return

        try:
            with self.storage_path.open("r", encoding="utf-8") as handle:
                data = json.load(handle)
        except (OSError, json.JSONDecodeError) as exc:
            LOGGER.warning("Failed to read job state from %s: %s", self.storage_path, exc)
            return

        if not isinstance(data, dict):
            LOGGER.warning("Ignoring invalid job state in %s", self.storage_path)
            return

        with self.lock:
            for job_id, state in data.items():
                if isinstance(state, dict) and "step" in state and "status" in state:
                    if state.get("status") == "running":
                        state["status"] = "interrupted"
                    self.jobs[job_id] = state


job_manager = JobManager()
