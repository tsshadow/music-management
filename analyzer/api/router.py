"""FastAPI router exposing analyzer functionality."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from analyzer.jobs.queue import get_queue
from scrobbler.app.core.settings import get_settings

router = APIRouter(prefix="/analyzer", tags=["analyzer"])


class ScanLibraryRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    force: bool = False


class EnrichListensRequest(BaseModel):
    since: datetime | None = None
    limit: int = Field(default=500, gt=0, le=5000)


class ConfirmMatchRequest(BaseModel):
    track_id: int
    learn_aliases: bool = True


def _enqueue(job_name: str, **kwargs) -> dict:
    settings = get_settings()
    queue = get_queue(settings.redis_url, settings.analyzer_queue_name)
    if not kwargs.get("paths") and job_name.endswith("scan_library_job"):
        kwargs["paths"] = settings.analyzer_default_paths
    if job_name.endswith("scan_library_job") and not kwargs.get("paths"):
        raise HTTPException(status_code=400, detail="No library paths configured")
    job = queue.enqueue(f"analyzer.jobs.handlers.{job_name}", kwargs={"dsn": settings.db_dsn, **kwargs})
    return {"job_id": job.id, "queued": True}


@router.post("/library/scan")
async def scan_library(payload: ScanLibraryRequest):
    """Queue a filesystem scan job for the analyzer."""

    return _enqueue("scan_library_job", paths=payload.paths, force=payload.force)


@router.post("/enrich/listens")
async def enrich_listens(payload: EnrichListensRequest):
    """Queue a listen enrichment job."""

    since = payload.since.isoformat() if payload.since else None
    return _enqueue("enrich_listens_job", since=since, limit=payload.limit)


@router.post("/reindex")
async def reindex_library():
    """Queue a reindex job to recompute track identifiers."""

    return _enqueue("reindex_library_job")


@router.post("/match/{listen_id}/confirm")
async def confirm_match(listen_id: int, payload: ConfirmMatchRequest):
    """Queue a confirmation job for an ambiguous listen."""

    return _enqueue(
        "confirm_listen_match_job",
        listen_id=listen_id,
        track_id=payload.track_id,
        learn_aliases=payload.learn_aliases,
    )
