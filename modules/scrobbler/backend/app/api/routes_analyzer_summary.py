"""Expose analyzer summary endpoints for the Scrobbler application."""

from __future__ import annotations

from fastapi import APIRouter, Depends

from analyzer.services.summary_service import AnalyzerSummaryService

from .deps import get_analyzer_summary_service

router = APIRouter(prefix="/analyzer", tags=["analyzer"])


@router.get("/summary")
async def get_analyzer_summary(
    service: AnalyzerSummaryService = Depends(get_analyzer_summary_service),
) -> dict:
    """Return aggregated metrics for the analyzer dashboard."""

    return await service.library_overview()
