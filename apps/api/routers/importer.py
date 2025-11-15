"""Importer specific API router."""

from __future__ import annotations

import logging
import os
from pathlib import Path
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, FastAPI, Header, HTTPException
from fastapi.concurrency import run_in_threadpool

from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector

from ..models.importer import (
    DownloadBatch,
    DownloadTask,
    DownloadedTrack,
    TagMutation,
    TaggingReport,
    TaggingTask,
)
from ..services.importer.download import DownloadHandler, DownloadService
from ..services.importer.jobs import build_websocket_router, job_manager
from ..services.importer.tagging import TaggingService
from ..utils import ensure_yt_dlp_is_updated
from modules.importer.api.config_store import ConfigStore
from pydantic import BaseModel
from modules.importer.api.db_init import ensure_tables_exist

router = APIRouter(prefix="/importer", tags=["importer"])

API_KEY = os.getenv("API_KEY")


async def _check_database() -> None:
    def _check() -> None:
        conn = DatabaseConnector().connect()
        conn.close()

    await run_in_threadpool(_check)


async def _start_background_jobs() -> None:
    ensure_tables_exist()


def register_importer(app: FastAPI) -> None:
    """Attach importer routes and lifecycle hooks to the shared app."""

    @app.on_event("startup")
    async def _startup() -> None:  # pragma: no cover - glue
        ensure_yt_dlp_is_updated()
        await _start_background_jobs()

    if not getattr(register_importer, "_ws_attached", False):
        router.include_router(build_websocket_router("/ws"))
        register_importer._ws_attached = True  # type: ignore[attr-defined]
    app.include_router(router, prefix="/api")


def verify_api_key(x_api_key: Optional[str] = Header(default=None)) -> None:
    if API_KEY and x_api_key != API_KEY:
        raise HTTPException(status_code=401, detail="Invalid API key")


@router.get("/health")
async def health() -> Dict[str, str]:
    try:
        await _check_database()
    except Exception as exc:  # pragma: no cover - defensive
        raise HTTPException(status_code=500, detail="Database connection failed") from exc
    return {"status": "ok"}


@router.get("/config")
async def get_config(_: None = Depends(verify_api_key)) -> Dict[str, Any]:
    store = ConfigStore()
    return {"fields": store.describe()}


class ConfigUpdatePayload(BaseModel):
    updates: Dict[str, Any]


@router.patch("/config")
async def update_config(
    payload: ConfigUpdatePayload,
    _: None = Depends(verify_api_key),
) -> Dict[str, Any]:
    store = ConfigStore()
    try:
        updated = store.update(payload.updates)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return {"values": updated}


@router.get("/accounts")
async def list_accounts(_: None = Depends(verify_api_key)) -> Dict[str, List[str]]:
    return {
        "soundcloud": _load_accounts("soundcloud_accounts"),
        "youtube": _load_accounts("youtube_accounts"),
    }


def _load_accounts(table: str) -> List[str]:
    try:
        conn = DatabaseConnector().connect()
    except Exception as exc:  # pragma: no cover - defensive
        logging.error("Failed to connect to database for %s accounts: %s", table, exc)
        return []

    try:
        with conn.cursor() as cursor:
            cursor.execute(f"SELECT name FROM {table}")
            accounts = [row[0] for row in cursor.fetchall()]
    except Exception as exc:  # pragma: no cover - defensive
        logging.error("Failed to fetch %s accounts: %s", table, exc)
        return []
    finally:
        conn.close()
    return sorted(accounts)


def _youtube_base_path() -> Path:
    folder = ConfigStore().get("youtube_folder")
    return Path(folder or "/downloads/youtube")


def _soundcloud_base_path() -> Path:
    folder = ConfigStore().get("soundcloud_folder")
    return Path(folder or "/downloads/soundcloud")


def _telegram_base_path() -> Path:
    folder = ConfigStore().get("telegram_folder")
    return Path(folder or "/downloads/telegram")


def _build_download_service() -> DownloadService:
    def youtube_handler(task: DownloadTask):
        base = _youtube_base_path()
        target = task.target or "batch"
        location = base / target
        yield DownloadedTrack(source="youtube", location=location)

    def soundcloud_handler(task: DownloadTask):
        base = _soundcloud_base_path()
        target = task.target or "batch"
        yield DownloadedTrack(source="soundcloud", location=base / target)

    def telegram_handler(task: DownloadTask):
        base = _telegram_base_path()
        target = task.target or "batch"
        yield DownloadedTrack(source="telegram", location=base / target)

    handlers: Dict[str, DownloadHandler] = {
        "youtube": youtube_handler,
        "manual": youtube_handler,
        "soundcloud": soundcloud_handler,
        "telegram": telegram_handler,
    }
    return DownloadService(handlers)


def _tagging_handler(track: DownloadedTrack, task: TaggingTask) -> TagMutation:
    return TagMutation(location=track.location, applied={"profile": task.profile})


_download_service = _build_download_service()
_tagging_service = TaggingService(_tagging_handler)


@router.post("/downloads", response_model=DownloadBatch)
async def create_download(
    tasks: List[DownloadTask],
    _: None = Depends(verify_api_key),
) -> DownloadBatch:
    return _download_service.execute(tasks)


@router.post("/tagging", response_model=TaggingReport)
async def create_tagging(
    task: TaggingTask,
    _: None = Depends(verify_api_key),
) -> TaggingReport:
    return _tagging_service.execute(task)


@router.get("/jobs")
async def list_jobs(_: None = Depends(verify_api_key)) -> Dict[str, List[Dict[str, Any]]]:
    return {"jobs": job_manager.recent()}


@router.get("/jobs/{job_id}")
async def get_job(job_id: str, _: None = Depends(verify_api_key)) -> Dict[str, Any]:
    job = job_manager.jobs.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job


__all__ = ["register_importer"]
