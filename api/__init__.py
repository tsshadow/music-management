"""Compatibility shim for the MuMa importer API package."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
_IMPORTER_ROOT = _REPO_ROOT / "modules" / "importer"
_PACKAGE_ROOT = _IMPORTER_ROOT / "api"

_SPEC = importlib.util.spec_from_file_location(
    __name__,
    _PACKAGE_ROOT / "__init__.py",
    submodule_search_locations=[str(_PACKAGE_ROOT)],
)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - defensive
    raise ImportError("Unable to load importer API package")

_module = importlib.util.module_from_spec(_SPEC)
sys.modules[__name__] = _module
sys.modules.setdefault("modules.importer.api", _module)
_SPEC.loader.exec_module(_module)
