"""Refreshing the preloaded lookup helpers.

`Cache.databaseHelpers` is constructed once, at import, and each `LookupTableHelper`
in it reads its whole table into memory in the constructor. That is the right trade
for tables the tagger reads thousands of times per run — and the wrong one the moment
a human edits those tables through the API, because the running process keeps
answering from the map it built at startup.

`LookupTableHelper` handles the general case itself by expiring its map (see
`STALE_AFTER_SECONDS`). This module handles the specific case: the process that just
wrote a rule should not have to wait out that interval before its own reply is
correct.

It lives beside Cache.py rather than inside it because importing Cache builds every
helper against a real database, which is exactly why services/tests/mock_base.py
replaces that module wholesale. A dispatcher that takes the mapping as an argument
can be tested on its own.
"""

import logging

logger = logging.getLogger(__name__)


def reload_helpers(helpers: dict, key: str | None = None) -> list[str]:
    """Rebuild one preloaded helper, or every one that supports it.

    :param helpers: the registry to act on, normally ``Cache.databaseHelpers``.
    :param key: a single registry key, or ``None`` for all of them.
    :returns: the keys that were actually reloaded.

    Nothing here raises. This runs at the end of a write that has already been
    committed, so a helper that cannot refresh must not turn a successful save into a
    500 — the caller would retry a write that already landed. A helper that fails
    keeps serving its previous map and expires on its own soon enough.
    """
    if key is None:
        targets = list(helpers.items())
    elif key in helpers:
        targets = [(key, helpers[key])]
    else:
        logger.warning('Asked to reload unknown helper %r', key)
        return []

    reloaded = []
    for name, helper in targets:
        reloader = getattr(helper, 'reload', None)
        if not callable(reloader):
            continue
        try:
            reloader()
        except Exception as e:  # pylint: disable=broad-except
            logger.error('Failed to reload helper %r: %s', name, e)
            continue
        reloaded.append(name)
    return reloaded
