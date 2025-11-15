"""Download pipeline service for the importer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, Dict, Iterable, List, Mapping
from uuid import uuid4

from ...models.importer import DownloadBatch, DownloadTask, DownloadedTrack
from .jobs import job_manager

DownloadHandler = Callable[[DownloadTask], Iterable[DownloadedTrack]]


class DownloadService:
    """Coordinates execution of importer download tasks."""

    def __init__(self, handlers: Mapping[str, DownloadHandler]) -> None:
        self._handlers: Dict[str, DownloadHandler] = dict(handlers)

    def sources(self) -> List[str]:
        return sorted(self._handlers.keys())

    def execute(self, tasks: Iterable[DownloadTask]) -> DownloadBatch:
        collected: List[DownloadedTrack] = []
        normalized_tasks = list(tasks)
        for task in normalized_tasks:
            handler = self._handlers.get(task.source)
            if handler is None:
                raise ValueError(f"Unsupported download source: {task.source}")
            for track in handler(task):
                collected.append(track)

        job_id = str(uuid4())
        job_manager.create(
            job_id,
            {
                "id": job_id,
                "status": "queued",
                "step": "download",
                "started": datetime.now(timezone.utc).isoformat(),
                "log": [],
            },
        )
        return DownloadBatch(
            job_id=job_id,
            created_at=datetime.now(timezone.utc),
            tasks=normalized_tasks,
            tracks=collected,
        )


__all__ = ["DownloadService", "DownloadHandler"]
