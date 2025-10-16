"""FastAPI router exposing analyzer functionality."""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field

from analyzer.jobs.queue import get_queue
from backend.app.core.settings import get_settings
from backend.app.db.adapter import DatabaseAdapter
from backend.app.api.deps import get_adapter

router = APIRouter(prefix="/analyzer", tags=["analyzer"])


class ScanLibraryRequest(BaseModel):
    paths: list[str] = Field(default_factory=list)
    force: bool = False
    split_paths: bool = Field(
        default=False,
        description=(
            "Queue an individual job per provided path instead of scanning them in a single "
            "worker. This helps parallelize large libraries with many top-level folders."
        ),
    )


class EnrichListensRequest(BaseModel):
    since: datetime | None = None
    limit: int = Field(default=500, gt=0, le=5000)


class ConfirmMatchRequest(BaseModel):
    track_id: int
    learn_aliases: bool = True


async def _load_scan_timeout(
    settings, adapter: DatabaseAdapter | None
) -> int:
    timeout = settings.analyzer_scan_job_timeout
    if not adapter:
        return timeout
    values = await adapter.get_config()
    override = values.get("analyzer_scan_job_timeout")
    if not override:
        return timeout
    try:
        parsed = int(override)
    except (TypeError, ValueError):
        return timeout
    if parsed < 60:
        return timeout
    return parsed


async def _enqueue(
    job_name: str,
    *,
    adapter: DatabaseAdapter | None = None,
    **kwargs,
) -> dict:
    settings = get_settings()
    queue = get_queue(settings.redis_url, settings.analyzer_queue_name)
    if not kwargs.get("paths") and job_name.endswith("scan_library_job"):
        kwargs["paths"] = settings.analyzer_default_paths
    if job_name.endswith("scan_library_job") and not kwargs.get("paths"):
        raise HTTPException(status_code=400, detail="No library paths configured")
    enqueue_kwargs: dict[str, object] = {}
    if job_name.endswith("scan_library_job"):
        enqueue_kwargs["job_timeout"] = await _load_scan_timeout(settings, adapter)
    job = queue.enqueue(
        f"analyzer.jobs.handlers.{job_name}",
        kwargs={"dsn": settings.db_dsn, **kwargs},
        **enqueue_kwargs,
    )
    return {"job_id": job.id, "queued": True}


@router.post("/library/scan")
async def scan_library(
    payload: ScanLibraryRequest, adapter: DatabaseAdapter = Depends(get_adapter)
):
    """Queue one or more filesystem scan jobs for the analyzer."""

    settings = get_settings()
    paths = list(payload.paths or settings.analyzer_default_paths)
    if payload.split_paths and paths:
        job_ids: list[str] = []
        for path in paths:
            result = await _enqueue(
                "scan_library_job",
                adapter=adapter,
                paths=[path],
                force=payload.force,
            )
            job_ids.append(result["job_id"])
        return {"job_ids": job_ids, "queued": True}
    return await _enqueue(
        "scan_library_job", adapter=adapter, paths=paths, force=payload.force
    )


@router.post("/enrich/listens")
async def enrich_listens(payload: EnrichListensRequest):
    """Queue a listen enrichment job."""

    since = payload.since.isoformat() if payload.since else None
    return await _enqueue(
        "enrich_listens_job", adapter=None, since=since, limit=payload.limit
    )


@router.post("/reindex")
async def reindex_library():
    """Queue a reindex job to recompute track identifiers."""

    return await _enqueue("reindex_library_job", adapter=None)


@router.post("/match/{listen_id}/confirm")
async def confirm_match(listen_id: int, payload: ConfirmMatchRequest):
    """Queue a confirmation job for an ambiguous listen."""

    return await _enqueue(
        "confirm_listen_match_job",
        adapter=None,
        listen_id=listen_id,
        track_id=payload.track_id,
        learn_aliases=payload.learn_aliases,
    )
