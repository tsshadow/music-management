"""Backward compatible FastAPI application for the importer module.

The canonical implementation now lives in :mod:`modules.importer.api.router` but
this module keeps the ``uvicorn api.server:app`` entrypoint working for local
tools and Docker images that have not yet been updated.
"""

from fastapi import FastAPI

from .router import importer_router, importer_shutdown, importer_startup, mount_frontend

app = FastAPI()


@app.on_event("startup")
async def _startup() -> None:  # pragma: no cover - thin wrapper
    await importer_startup()


@app.on_event("shutdown")
async def _shutdown() -> None:  # pragma: no cover - thin wrapper
    await importer_shutdown()


app.include_router(importer_router)
mount_frontend(app)
