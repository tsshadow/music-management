"""Compatibility shim for the MuMa importer step module."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_MODULE_PATH = _REPO_ROOT / "modules" / "importer" / "step.py"

_SPEC = importlib.util.spec_from_file_location(__name__, _MODULE_PATH)
if _SPEC is None or _SPEC.loader is None:  # pragma: no cover - defensive
    raise ImportError("Unable to load importer step module")

_module = importlib.util.module_from_spec(_SPEC)
sys.modules[__name__] = _module
sys.modules.setdefault("modules.importer.step", _module)
_SPEC.loader.exec_module(_module)
