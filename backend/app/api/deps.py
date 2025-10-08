from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request, status

from ..core.settings import get_settings


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
