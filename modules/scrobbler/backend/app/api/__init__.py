"""Dynamic import helpers for FastAPI route modules."""

from __future__ import annotations

import importlib
from types import ModuleType
from typing import Dict

__all__ = [
    "routes_config",
    "routes_enrichment",
    "routes_export",
    "routes_import",
    "routes_library",
    "routes_listens",
    "routes_scrobble",
    "routes_stats",
    "routes_subsonic",
    "routes_analyzer",
    "routes_analyzer_summary",
]

_MODULE_CACHE: Dict[str, ModuleType] = {}


def __getattr__(name: str) -> ModuleType:
    """Lazily import API route modules on first access."""

    if name not in __all__:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    if name not in _MODULE_CACHE:
        _MODULE_CACHE[name] = importlib.import_module(f"{__name__}.{name}")
    return _MODULE_CACHE[name]


def __dir__() -> list[str]:  # pragma: no cover - convenience
    return sorted(list(__all__) + [key for key in globals() if not key.startswith("_")])
