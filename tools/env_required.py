"""Read required settings from the environment, with no default and a clear error.

The ad-hoc tools and scripts talk to whatever database or host the environment names. None of
them may guess one: a missing variable stops the run with exit code 2 and the names of all
that are missing, instead of connecting somewhere nobody chose.
"""

from __future__ import annotations

import os
import sys
from collections.abc import Mapping

MISSING_EXIT_CODE = 2


def require_env(*names: str, environ: Mapping[str, str] | None = None) -> dict[str, str]:
    """Return `{name: value}` for every name; exit with code 2 naming each one that is unset or empty."""
    source = os.environ if environ is None else environ
    values = {name: source.get(name, '') for name in names}
    missing = [name for name, value in values.items() if not value]
    if missing:
        print(f'Missing environment variable(s): {", ".join(missing)}. Set them and run again.', file=sys.stderr)
        raise SystemExit(MISSING_EXIT_CODE)
    return values
