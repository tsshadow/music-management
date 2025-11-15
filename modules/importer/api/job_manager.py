"""Compatibility layer exposing the new importer job manager."""

from __future__ import annotations

from apps.api.services.importer.jobs import JobManager, build_websocket_router, job_manager

__all__ = ["JobManager", "job_manager", "build_websocket_router"]
