"""RQ queue helpers."""

from __future__ import annotations

from functools import lru_cache

from redis import Redis
from rq import Queue

__all__ = ["get_queue"]


@lru_cache(maxsize=1)
def get_queue(url: str, name: str = "scrobbler-analyzer") -> Queue:
    """Return an RQ queue instance for the analyzer."""

    connection = Redis.from_url(url)
    return Queue(name, connection=connection)
