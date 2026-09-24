"""Progress of the background jobs the curation pages start, kept in this process.

The artist and genre analysis runs (`routers/artist_curation.py`, `routers/genre_curation.py`)
and a rule's retag (`routers/curation.py`) run as FastAPI background tasks; the page polls the
router's own status route for the job id it was handed. This is where that state lives.

It used to be the `job_manager` of `routers/jobs.py`, which also carried an HTTP registry for
worker processes (`/api/jobs/register`, `/active`, `/history`) and an unauthenticated WebSocket.
Nothing ever pushed to or read from those -- the workers' side only pushed when `HUB_API_URL` was
set, and no deployment set it -- so they were removed, and with them the leak: finished jobs were
never dropped. Here a finished job is kept for the last `KEEP_FINISHED` jobs only.
"""

from __future__ import annotations

import threading
from collections import deque
from typing import Any

#: How many finished jobs keep their final state around for a late poll.
KEEP_FINISHED = 50


class JobStore:
    """`jobs` holds every queued or running job's live state (and a finished one's, until it
    is evicted); `results` holds a finished job's final state; `history` is finished job ids,
    newest first."""

    def __init__(self, keep_finished: int = KEEP_FINISHED) -> None:
        self.jobs: dict[str, dict[str, Any]] = {}
        self.results: dict[str, dict[str, Any]] = {}
        self.history: deque[str] = deque()
        self.keep_finished = keep_finished
        self._lock = threading.Lock()

    def finish(self, job_id: str, state: dict[str, Any]) -> None:
        """Record `state` as the final state of `job_id`, and forget the oldest finished
        jobs beyond `keep_finished`. Finishing the same job twice keeps one history entry."""
        with self._lock:
            self.results[job_id] = dict(state)
            if job_id in self.history:
                return
            self.history.appendleft(job_id)
            while len(self.history) > self.keep_finished:
                oldest = self.history.pop()
                self.results.pop(oldest, None)
                self.jobs.pop(oldest, None)

    def state(self, job_id: str) -> dict[str, Any] | None:
        """The live state of `job_id`, else its final state, else None."""
        return self.jobs.get(job_id) or self.results.get(job_id)


job_store = JobStore()
