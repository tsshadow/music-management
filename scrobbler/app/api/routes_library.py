from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException

from ..db.adapter import DatabaseAdapter
from .deps import get_adapter, verify_api_key

router = APIRouter(prefix="/library", tags=["library"], dependencies=[Depends(verify_api_key)])


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
