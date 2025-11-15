"""Utilities for orchestrating importer steps from the API layer."""

from __future__ import annotations

import asyncio
import copy
import logging
from collections import deque
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Deque, Dict, Iterable, List, Optional
from uuid import uuid4

try:  # pragma: no cover - imported for its side effects at runtime
    from modules.importer.api.steps import steps_to_run
except Exception:  # pragma: no cover - modules package may be unavailable in some envs
    steps_to_run = []  # type: ignore

from .jobs import job_manager


logger = logging.getLogger(__name__)


def _normalize_selectors(selectors: Iterable[str]) -> List[str]:
    return [selector for selector in selectors if selector]


def _convert_kwargs(options: Dict[str, object]) -> Dict[str, object]:
    """Translate snake_case options into the legacy camelCase arguments."""

    translated: Dict[str, object] = {}
    for key, value in options.items():
        if key == "break_on_existing":
            translated["breakOnExisting"] = value
        else:
            translated[key] = value
    return translated


class ImporterPipeline:
    """Thin wrapper that executes importer steps on demand."""

    def __init__(self, steps: Optional[Iterable] = None) -> None:
        self._steps = list(steps or steps_to_run)

    def run(self, selectors: Iterable[str], **options: object) -> List[str]:
        """Execute all steps that match any of *selectors*.

        Returns a list of job identifiers registered in :mod:`job_manager`.
        """

        normalized = _normalize_selectors(selectors)
        if not normalized:
            raise ValueError("At least one selector must be provided")

        job_ids: List[str] = []
        translated = _convert_kwargs(options)
        for step in self._steps:
            job_id = step.run(normalized, **translated)
            if job_id:
                job_ids.append(job_id)
        return job_ids

    def run_job(self, kind: str, **options: object) -> List[str]:
        """Execute a predefined importer job."""

        mapping = {
            "import": ["import"],
            "download-youtube": ["download-youtube"],
            "download-soundcloud": ["download-soundcloud"],
            "download-telegram": ["download-telegram"],
            "tag": ["tag"],
            "tag-soundcloud": ["tag-soundcloud"],
            "tag-youtube": ["tag-youtube"],
            "tag-telegram": ["tag-telegram"],
            "tag-labels": ["tag-labels"],
            "tag-generic": ["tag-generic"],
            "manual-youtube": ["manual-youtube"],
            "manual-soundcloud": ["manual-soundcloud"],
        }

        selectors = mapping.get(kind)
        if not selectors:
            raise ValueError(f"Unsupported importer job: {kind}")
        return self.run(selectors, **options)


@dataclass
class JobRunRecord:
    job_ids: List[str]
    started_at: datetime
    completed_at: Optional[datetime] = None
    details: List[Dict[str, object]] = field(default_factory=list)


@dataclass
class RecurringJob:
    """Book-keeping structure for scheduled importer jobs."""

    job_id: str
    kind: str
    interval: float
    options: Dict[str, object]
    repeat: bool = True
    started_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))
    runs: int = 0
    last_run_at: Optional[datetime] = None
    last_job_ids: List[str] = field(default_factory=list)
    task: Optional[asyncio.Task] = None
    history: Deque[JobRunRecord] = field(default_factory=lambda: deque(maxlen=10))


class RecurringJobManager:
    """Manage importer jobs that should repeat on a schedule."""

    def __init__(self, pipeline: ImporterPipeline) -> None:
        self._pipeline = pipeline
        self._jobs: Dict[str, RecurringJob] = {}

    def list(self) -> List[RecurringJob]:
        return list(self._jobs.values())

    def describe(self) -> List[Dict[str, object]]:
        return [self._describe(job) for job in self.list()]

    async def run_once(self, kind: str, **options: object) -> JobRunRecord:
        started = datetime.now(timezone.utc)
        job_ids = await asyncio.to_thread(self._pipeline.run_job, kind, **options)
        details = self._collect_job_details(job_ids)
        return JobRunRecord(
            job_ids=job_ids,
            started_at=started,
            completed_at=datetime.now(timezone.utc),
            details=details,
        )

    async def start(self, kind: str, interval: float, **options: object) -> RecurringJob:
        if interval <= 0:
            raise ValueError("Interval must be greater than zero")

        job = RecurringJob(
            job_id=str(uuid4()),
            kind=kind,
            interval=interval,
            options=dict(options),
        )

        async def _runner() -> None:
            while True:
                try:
                    record = await self.run_once(kind, **options)
                    job.runs += 1
                    job.last_job_ids = record.job_ids
                    job.last_run_at = record.completed_at
                    job.history.append(record)
                except Exception:  # pragma: no cover - defensive logging
                    logger.exception("Recurring importer job %s failed", job.job_id)
                    raise
                await asyncio.sleep(interval)

        job.task = asyncio.create_task(_runner())
        self._jobs[job.job_id] = job
        return job

    def cancel(self, job_id: str) -> None:
        record = self._jobs.get(job_id)
        if not record:
            return
        if record.task and not record.task.done():
            record.task.cancel()
        self._jobs.pop(job_id, None)

    def _collect_job_details(self, job_ids: Iterable[str]) -> List[Dict[str, object]]:
        details: List[Dict[str, object]] = []
        for job_id in job_ids:
            data = job_manager.results.get(job_id) or job_manager.jobs.get(job_id)
            if data:
                details.append(copy.deepcopy(data))
        return details

    def _describe(self, job: RecurringJob) -> Dict[str, object]:
        return {
            "job_id": job.job_id,
            "kind": job.kind,
            "repeat": job.repeat,
            "interval": int(job.interval) if job.repeat else None,
            "started_at": job.started_at,
            "runs": job.runs,
            "last_run_at": job.last_run_at,
            "last_job_ids": list(job.last_job_ids),
            "options": dict(job.options),
            "history": [
                {
                    "job_ids": list(record.job_ids),
                    "started_at": record.started_at,
                    "completed_at": record.completed_at,
                    "details": record.details,
                }
                for record in job.history
            ],
        }


pipeline = ImporterPipeline()
recurring_jobs = RecurringJobManager(pipeline)


__all__ = [
    "ImporterPipeline",
    "JobRunRecord",
    "RecurringJob",
    "RecurringJobManager",
    "pipeline",
    "recurring_jobs",
]
