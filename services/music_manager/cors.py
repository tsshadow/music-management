"""Which browser origins may call this API.

It used to be every origin, with every method and header. That is not an auth
bypass on its own -- credentials are off, so a browser attaches nothing and a
caller needs the x-api-key already -- but it does let any page a victim opens
read the unauthenticated endpoints from inside this network.

In practice almost nothing needs it: the web UI is served by the LMS server,
which proxies /api on the same origin, and MuMa Mobile is not a browser and is
not subject to CORS at all. The default below is therefore the development
origins only, and a deployment that needs more says so.
"""
from __future__ import annotations

import logging

# Vite's dev server, and the LMS server when it is run directly.
DEFAULT_ORIGINS = (
    'http://localhost:5173',
    'http://127.0.0.1:5173',
    'http://localhost:5082',
    'http://127.0.0.1:5082',
)

# Everything the browser clients actually send. Listing them beats '*' because a
# method that appears here later is a decision someone made.
ALLOWED_METHODS = ('GET', 'POST', 'PUT', 'PATCH', 'DELETE', 'OPTIONS')


def allowed_origins(setting: str | None, logger: logging.Logger | None = None) -> list[str]:
    """The origin allowlist, from a comma-separated setting.

    `*` is still available and still means every origin -- this is a narrowing of
    the default, not the removal of an option. That matters operationally: if a
    browser client nobody remembered turns out to need it, setting
    MUMA_CORS_ORIGINS=* restores the old behaviour without deploying new code.
    """
    if setting is None or not setting.strip():
        if logger:
            logger.info(
                'MUMA_CORS_ORIGINS is not set; allowing only the development origins. '
                'Set it to the browser origins this deployment serves, or to * to allow all.'
            )
        return list(DEFAULT_ORIGINS)

    origins = [part.strip() for part in setting.split(',') if part.strip()]

    if '*' in origins:
        if logger:
            logger.warning('MUMA_CORS_ORIGINS allows every origin.')
        return ['*']

    return origins
