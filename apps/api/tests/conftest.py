"""Test configuration for the FastAPI importer services suite."""

from __future__ import annotations

import sys
from pathlib import Path

# The tests are executed with ``cwd`` pointing at ``apps/api`` in CI.  Ensure the
# repository root is present on ``sys.path`` so ``import apps`` succeeds.
REPO_ROOT = Path(__file__).resolve().parents[3]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))
