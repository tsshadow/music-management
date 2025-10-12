from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from analyzer.services.library_stats_service import AnalyzerLibraryStatsService

from ..db.adapter import DatabaseAdapter
from .deps import (
    get_adapter,
    get_analyzer_library_stats_service,
    verify_api_key,
)

router = APIRouter(prefix="/library", tags=["library"], dependencies=[Depends(verify_api_key)])


@router.get("/artists")
async def library_artists(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    service: AnalyzerLibraryStatsService = Depends(get_analyzer_library_stats_service),
):
    """Return artists ranked by the number of songs in the library."""

    data = await service.artists(limit=page_size, offset=(page - 1) * page_size)
    return {**data, "page": page, "page_size": page_size}


@router.get("/albums")
async def library_albums(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    service: AnalyzerLibraryStatsService = Depends(get_analyzer_library_stats_service),
):
    """Return albums ranked by the number of songs in the library."""

    data = await service.albums(limit=page_size, offset=(page - 1) * page_size)
    return {**data, "page": page, "page_size": page_size}


@router.get("/genres")
async def library_genres(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    service: AnalyzerLibraryStatsService = Depends(get_analyzer_library_stats_service),
):
    """Return genres ranked by the number of songs in the library."""

    data = await service.genres(limit=page_size, offset=(page - 1) * page_size)
    return {**data, "page": page, "page_size": page_size}


@router.get("/tracks")
async def library_tracks(
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=500),
    service: AnalyzerLibraryStatsService = Depends(get_analyzer_library_stats_service),
):
    """Return tracks registered in the analyzer library."""

    data = await service.tracks(limit=page_size, offset=(page - 1) * page_size)
    return {**data, "page": page, "page_size": page_size}


@router.get("/artists/{artist_id}/insights")
async def artist_insights(artist_id: int, adapter: DatabaseAdapter = Depends(get_adapter)):
    """Return aggregated listen insights for a single artist."""

    data = await adapter.artist_insights(artist_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Artist not found")
    return data


@router.get("/albums/{album_id}/insights")
async def album_insights(album_id: int, adapter: DatabaseAdapter = Depends(get_adapter)):
    """Return aggregated listen insights for a single album."""

    data = await adapter.album_insights(album_id)
    if data is None:
        raise HTTPException(status_code=404, detail="Album not found")
    return data
