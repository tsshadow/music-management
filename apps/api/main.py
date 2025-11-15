"""Combined FastAPI application for the MuMa platform."""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Iterable

import logging

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Ensure the legacy ``modules`` packages remain importable when the server is
# started from nested working directories (e.g. ``apps``).  The importer and
# scrobbler code rely on their historical top-level package names, so we prepend
# their locations to ``sys.path`` before importing any routers.
_REPO_ROOT = Path(__file__).resolve().parents[2]
_MODULES_DIR = _REPO_ROOT / "modules"
for package in ("importer", "scrobbler"):
    candidate = _MODULES_DIR / package
    if candidate.is_dir():
        candidate_path = str(candidate)
        if candidate_path not in sys.path:
            sys.path.insert(0, candidate_path)

from .frontend import register_frontend
from .routers.importer import register_importer
from .routers.scrobbler import register_scrobbler

logger = logging.getLogger(__name__)


def _trusted_origins() -> Iterable[str]:
    raw = os.getenv("CORS_ORIGINS", "*")
    for origin in (value.strip() for value in raw.split(",")):
        if origin:
            yield origin


def create_app() -> FastAPI:
    """Instantiate the shared FastAPI application.

    The application wires the importer and scrobbler/analyzer routers together
    so they share authentication, middleware, and lifecycle hooks. Individual
    routers can still attach their own startup/shutdown callbacks – they are
    registered against the shared instance here.
    """

    app = FastAPI(title="MuMa API")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=list(_trusted_origins()) or ["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    register_importer(app)
    register_scrobbler(app)

    missing_frontend = register_frontend(app)
    if missing_frontend:
        logger.warning("Frontend build missing at %s", missing_frontend)
    return app


app = create_app()

__all__ = ["app", "create_app"]
