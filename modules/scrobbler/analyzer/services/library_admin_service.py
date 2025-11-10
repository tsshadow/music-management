"""Administrative helpers for destructive analyzer operations."""

from __future__ import annotations

from analyzer.db.repo import AnalyzerRepository

__all__ = ["AnalyzerLibraryAdminService"]


class AnalyzerLibraryAdminService:
    """Expose maintenance helpers for the analyzer-managed media library."""

    def __init__(self, repo: AnalyzerRepository) -> None:
        """Store the repository used to mutate analyzer tables."""

        self.repo = repo

    async def clear_library(self) -> dict[str, int]:
        """Delete analyzer-owned media library rows while keeping files intact."""

        return await self.repo.reset_library()
