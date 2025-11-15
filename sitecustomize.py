"""Repository-wide site customizations for MuMa."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent
_MODULES_DIR = _REPO_ROOT / "modules"


def _prepend_module(path: Path) -> None:
    if not path.is_dir():
        return
    as_str = str(path)
    if as_str not in sys.path:
        sys.path.insert(0, as_str)


for package in ("importer", "scrobbler"):
    _prepend_module(_MODULES_DIR / package)

importer_sitecustomize = _MODULES_DIR / "importer" / "sitecustomize.py"
if importer_sitecustomize.exists():
    spec = importlib.util.spec_from_file_location(
        "_muma_importer_sitecustomize", importer_sitecustomize
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules.setdefault(spec.name, module)
    if spec.loader is not None:
        spec.loader.exec_module(module)
