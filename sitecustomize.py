"""Repository-wide site customizations for MuMa."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_IMPORTER_DIR = _REPO_ROOT / "modules" / "importer"

# Ensure the importer package is importable regardless of the working directory.
if _IMPORTER_DIR.is_dir():
    importer_path = str(_IMPORTER_DIR)
    if importer_path not in sys.path:
        sys.path.insert(0, importer_path)

    importer_sitecustomize = _IMPORTER_DIR / "sitecustomize.py"
    if importer_sitecustomize.exists():
        spec = importlib.util.spec_from_file_location(
            "_muma_importer_sitecustomize", importer_sitecustomize
        )
        module = importlib.util.module_from_spec(spec)
        sys.modules.setdefault(spec.name, module)
        if spec.loader is not None:
            spec.loader.exec_module(module)
