"""Tagging pipeline service for the importer."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Callable, List
from uuid import uuid4

from ...models.importer import DownloadedTrack, TagMutation, TaggingReport, TaggingTask
from .jobs import job_manager

TaggingHandler = Callable[[DownloadedTrack, TaggingTask], TagMutation]


class TaggingService:
    """Apply metadata to downloaded tracks via injectable handlers."""

    def __init__(self, handler: TaggingHandler) -> None:
        self._handler = handler

    def execute(self, task: TaggingTask) -> TaggingReport:
        mutations: List[TagMutation] = []
        for track in task.tracks:
            mutations.append(self._handler(track, task))

        job_id = str(uuid4())
        job_manager.create(
            job_id,
            {
                "id": job_id,
                "status": "queued",
                "step": "tag",
                "started": datetime.now(timezone.utc).isoformat(),
                "log": [],
            },
        )

        return TaggingReport(
            job_id=job_id,
            created_at=datetime.now(timezone.utc),
            profile=task.profile,
            mutations=mutations,
        )


__all__ = ["TaggingService", "TaggingHandler"]
