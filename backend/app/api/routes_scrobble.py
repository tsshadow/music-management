from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ..schemas.common import ScrobblePayload
from ..services.ingest_service import IngestService
from .deps import get_ingest_service, verify_api_key

router = APIRouter(prefix="/scrobble", tags=["scrobble"])


@router.post("", status_code=201, dependencies=[Depends(verify_api_key)])
async def ingest_scrobble(
    payload: ScrobblePayload,
    service: IngestService = Depends(get_ingest_service),
):
    """Store a scrobble payload and return the created listen identifier."""

    listen_id = await service.ingest(payload)
    return {"listen_id": listen_id}
