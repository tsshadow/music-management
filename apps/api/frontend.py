"""Utility helpers to expose the built SvelteKit frontend through FastAPI."""

from __future__ import annotations

from pathlib import Path
from typing import Optional

from fastapi import APIRouter, FastAPI, HTTPException
from fastapi.responses import FileResponse

_REPO_ROOT = Path(__file__).resolve().parents[2]
_FRONTEND_BUILD = _REPO_ROOT / "apps" / "web" / "build"
_INDEX_FILE = _FRONTEND_BUILD / "index.html"


def _resolve_asset(path: str) -> Optional[Path]:
    """Return a file within the frontend build directory if it exists."""

    target = (_FRONTEND_BUILD / path).resolve()
    try:
        target.relative_to(_FRONTEND_BUILD.resolve())
    except ValueError:
        return None
    if target.is_file():
        return target
    return None


def register_frontend(app: FastAPI) -> Optional[Path]:
    """Expose the static frontend build if it is available.

    Returns the expected build directory when the assets are missing so the
    caller can log a helpful warning. The API is still usable without the
    frontend, which is important for CI environments.
    """

    if not _INDEX_FILE.exists():
        return _FRONTEND_BUILD

    router = APIRouter()

    @router.get("/", include_in_schema=False)
    async def frontend_index() -> FileResponse:
        return FileResponse(_INDEX_FILE)

    @router.get("/{path:path}", include_in_schema=False)
    async def frontend_files(path: str) -> FileResponse:
        asset = _resolve_asset(path)
        if asset:
            return FileResponse(asset)
        if path == "api" or path.startswith("api/"):
            raise HTTPException(status_code=404, detail="Not Found")
        return FileResponse(_INDEX_FILE)

    app.include_router(router)
    return None


__all__ = ["register_frontend"]
