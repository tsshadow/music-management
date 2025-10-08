from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ..db.adapter import DatabaseAdapter
from .deps import get_adapter, verify_api_key

router = APIRouter(prefix="/listens", tags=["listens"])


@router.get("/recent", dependencies=[Depends(verify_api_key)])
async def recent_listens(
    limit: int = Query(10, ge=1, le=100),
    adapter: DatabaseAdapter = Depends(get_adapter),
):
    return await adapter.fetch_recent_listens(limit=limit)


@router.get("/count", dependencies=[Depends(verify_api_key)])
async def listen_count(adapter: DatabaseAdapter = Depends(get_adapter)):
    count = await adapter.count_listens()
    return {"count": count}
