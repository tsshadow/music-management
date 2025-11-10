from __future__ import annotations

from fastapi import APIRouter, Depends

from ..schemas.common import ScrobblePayload
from ..services.enrichment_queue_service import EnrichmentQueueService
from ..services.ingest_service import IngestService
from .deps import (
    get_enrichment_queue_service,
    get_ingest_service,
    verify_api_key,
)

router = APIRouter(prefix="/scrobble", tags=["scrobble"])


@router.post("", status_code=201, dependencies=[Depends(verify_api_key)])
async def ingest_scrobble(
    payload: ScrobblePayload,
    service: IngestService = Depends(get_ingest_service),
    enrichment_queue: EnrichmentQueueService = Depends(get_enrichment_queue_service),
):
    """Store a scrobble payload and return the created listen identifier."""

    listen_id, created = await service.ingest_with_status(payload)
    enrich_job_id: str | None = None
    if created:
        enrich_job_id = enrichment_queue.queue_enrich(since=payload.listened_at)
    return {"listen_id": listen_id, "enrich_job_id": enrich_job_id}
