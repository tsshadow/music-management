"""High level summary helpers for the analyzer module."""

from __future__ import annotations

from analyzer.db.repo import AnalyzerRepository

__all__ = ["AnalyzerSummaryService"]


class AnalyzerSummaryService:
    """Expose aggregated analyzer metrics for API consumers."""

    def __init__(self, repo: AnalyzerRepository) -> None:
        """Store the repository instance used to query analyzer data."""

        self.repo = repo

    async def library_overview(self) -> dict:
        """Return the analyzer library summary payload."""

        return await self.repo.fetch_library_summary()
