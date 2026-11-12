"""``python -m tools.muma_ro`` and the zipapp: ``--priv`` first selects the root helper."""

from __future__ import annotations

import sys

from tools.muma_ro.cli import main, main_priv


def entry() -> int:
    """Dispatch to the helper when the first argument is ``--priv``, else to ``muma-ro``."""
    args = sys.argv[1:]
    if args[:1] == ['--priv']:
        return main_priv(args[1:])
    return main(args)


if __name__ == '__main__':
    sys.exit(entry())
