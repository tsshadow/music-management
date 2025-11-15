"""Combined FastAPI application for the MuMa platform."""

from __future__ import annotations

import os
from typing import Iterable

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers.importer import register_importer
from .routers.scrobbler import register_scrobbler


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
    return app


app = create_app()

__all__ = ["app", "create_app"]
