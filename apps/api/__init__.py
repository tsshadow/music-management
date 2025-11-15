"""Application package for the combined MuMa FastAPI backend."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:  # pragma: no cover - only for type checkers
    from .main import create_app as create_app


def create_app():  # type: ignore[override]
    """Lazy importer that defers heavy FastAPI imports until needed."""

    from .main import create_app as _create_app

    return _create_app()


__all__ = ["create_app"]
