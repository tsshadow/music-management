from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status

from ..core.settings import get_settings
from ..services.listenbrainz_export_service import ListenBrainzExportService
from ..services.listenbrainz_service import ListenBrainzImportService


async def verify_api_key(request: Request, x_api_key: str | None = Header(default=None)) -> None:
    """Validate the optional API key header against the configured value."""

    settings = get_settings()
    expected = settings.api_key
    if expected and expected != x_api_key:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid API key")


def get_ingest_service(request: Request):
    """Return the ingestion service bound to the FastAPI application state."""

    return request.app.state.ingest_service


def get_adapter(request: Request):
    """Return the database adapter used by the application."""

    return request.app.state.db_adapter


def get_stats_service(request: Request):
    """Return the statistics service bound to the FastAPI application state."""

    return request.app.state.stats_service


def get_listenbrainz_service(request: Request) -> ListenBrainzImportService:
    """Return the ListenBrainz import service bound to the application state."""

    return request.app.state.listenbrainz_service


def get_listenbrainz_export_service(request: Request) -> ListenBrainzExportService:
    """Return the ListenBrainz export service bound to the application state."""

    return request.app.state.listenbrainz_export_service
