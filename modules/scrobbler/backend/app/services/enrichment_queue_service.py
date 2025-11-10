"""Utilities for queueing analyzer enrichment jobs from the scrobbler."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from analyzer.jobs.queue import get_queue

from ..core.settings import AppSettings


class EnrichmentQueueService:
    """Queue listen enrichment jobs that link scrobbles to library tracks."""

    def __init__(self, settings: AppSettings) -> None:
        """Store application settings used to build job parameters."""

        self._settings = settings

    def queue_enrich(self, *, since: datetime | None = None, limit: int = 500) -> str:
        """Enqueue a listen enrichment job and return the job identifier."""

        queue = get_queue(self._settings.redis_url, self._settings.analyzer_queue_name)
        payload: dict[str, Any] = {"dsn": self._settings.db_dsn, "limit": limit}
        if since is not None:
            payload["since"] = since.isoformat()
        job = queue.enqueue("analyzer.jobs.handlers.enrich_listens_job", kwargs=payload)
        return job.id
