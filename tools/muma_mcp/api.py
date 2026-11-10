"""HTTP client for the production management endpoints.

Three endpoints, all read-only, all already deployed:

- ``GET /health`` -- reports the running version and every background thread
  to a caller with a key; without one it answers the status alone (issue #218). This is the honest answer to "what is live", more honest
  than a git tag, which has been created for a version production never received.
- ``GET /api/system/containers``
- ``GET /api/system/logs/{name}?tail=``

Note the prefix is ``/api``, not ``/api/management``: ``main.py`` mounts the
management router with ``prefix="/api"`` and the router itself declares no prefix
of its own.
"""

from __future__ import annotations

from typing import Any

import requests

from tools.muma_mcp.config import Config
from tools.muma_mcp.redact import redact

TIMEOUT_SECONDS = 10


class ProdApiError(RuntimeError):
    """The API could not be reached, or answered with an error."""


def _get(config: Config, path: str, *, authenticated: bool, params: dict[str, Any] | None = None) -> Any:
    """GET `path` on production and return its JSON.

    `/api/...` goes to ``config.api_base`` (``MUMA_PROD_API_URL``), anything else, i.e.
    `/health`, to ``config.prod_url``: through nginx the two live under different prefixes.
    """
    headers = {'X-API-Key': config.api_key} if authenticated else {}
    base = config.api_base if path.startswith('/api/') else config.prod_url
    url = f'{base}{path}'
    try:
        response = requests.get(url, headers=headers, params=params, timeout=TIMEOUT_SECONDS)
    except requests.RequestException as exc:
        raise ProdApiError(
            f'{url} niet bereikbaar: {exc}. '
            'In een gesandboxte sessie is het LAN onbereikbaar; dat is geen storing op prod.'
        ) from exc

    if response.status_code in (401, 403):
        raise ProdApiError(f'{path} weigerde de API-sleutel (HTTP {response.status_code})')
    if not response.ok:
        raise ProdApiError(f'{path} gaf HTTP {response.status_code}')

    try:
        return response.json()
    except ValueError as exc:
        # The LMS proxy gate answers bursts with a plain-text "Too many requests",
        # which surfaces as a JSON decode error naming the wrong component.
        snippet = response.text[:120]
        raise ProdApiError(f'{path} gaf geen JSON terug: {snippet!r}') from exc


def health(config: Config) -> Any:
    """The deployed version and the state of every background thread."""
    return _get(config, '/health', authenticated=True)


def containers(config: Config) -> Any:
    """Name, status and image of the muma, database and LMS containers."""
    return _get(config, '/api/system/containers', authenticated=True)


def logs(config: Config, name: str, tail: int = 200) -> str:
    """The tail of one container's log, with secrets masked.

    Masking is best-effort: it catches the known values and the usual shapes, not
    every conceivable one. Treat the result as sensitive anyway.
    """
    tail = max(1, min(int(tail), 2000))
    payload = _get(config, f'/api/system/logs/{name}', authenticated=True, params={'tail': tail})
    raw = payload.get('logs', '') if isinstance(payload, dict) else str(payload)
    return redact(raw, config.secrets)
