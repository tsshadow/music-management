"""Maintenance helpers for consolidating duplicated listens."""

from __future__ import annotations

from ..db.adapter import DatabaseAdapter


class DeduplicationService:
    """Coordinate database-level deduplication tasks for listens."""

    def __init__(self, adapter: DatabaseAdapter) -> None:
        """Store the database adapter used to perform deduplication work."""

        self.adapter = adapter

    async def deduplicate(self) -> int:
        """Merge duplicate listens and return how many rows were removed."""

        return await self.adapter.deduplicate_listens()
