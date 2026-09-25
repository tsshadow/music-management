"""Deprecated routes: make real usage visible before anything is removed.

A route with no consumer in this repository may still have one outside it -- a Home
Assistant sensor, a script on someone's laptop, a bookmark. Neither the code search
nor the event log proves otherwise, so a route is deprecated first and removed only
after the removal date has passed without it showing up.

Mark a route with ``deprecated=True, dependencies=[DEPRECATED_CALL]``: FastAPI flags it
in the OpenAPI schema, and the first call per route per process logs one INFO line with
the caller's address. The logger sits under ``music-manager`` so the line reaches the
event log (``/api/events``), which is where the usage check looks.
See docs/bug-reports/084-unused-endpoints-and-duplicate-normalizers.md.
"""

import logging
import threading

from fastapi import Depends, Request

#: The date after which a deprecated route that nobody called may be deleted.
REMOVAL_DATE = '2026-11-01'

logger = logging.getLogger('music-manager.deprecation')

_seen: set[tuple[str, str]] = set()
_lock = threading.Lock()


def _route_key(request: Request) -> tuple[str, str]:
    """(method, handler) -- keyed on the handler, so every id of one route counts once.

    Not on the route's path: on an included router that is the path *without* its
    prefix, and two routers can both own a `/sources`.
    """
    endpoint = request.scope.get('endpoint')
    handler = f'{endpoint.__module__}.{endpoint.__qualname__}' if endpoint else request.url.path
    return request.method, handler


def log_deprecated_call(request: Request) -> None:
    """Log the first call of a deprecated route in this process, with who made it."""
    key = _route_key(request)
    with _lock:
        if key in _seen:
            return
        _seen.add(key)
    caller = request.client.host if request.client else 'unknown'
    logger.info(
        'Deprecated endpoint %s %s (%s) called by %s; scheduled for removal on %s',
        request.method,
        request.url.path,
        key[1],
        caller,
        REMOVAL_DATE,
    )


def reset_seen() -> None:
    """Forget which routes were already logged. For tests."""
    with _lock:
        _seen.clear()


#: The dependency to attach to a deprecated route.
DEPRECATED_CALL = Depends(log_deprecated_call)
