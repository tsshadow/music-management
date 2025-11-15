"""Compatibility shim for the importer job websocket router."""

from __future__ import annotations

from apps.api.services.importer.jobs import build_websocket_router, job_manager

__all__ = ["job_manager", "build_websocket_router"]
