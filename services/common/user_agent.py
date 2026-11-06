"""The one place that builds the User-Agent string for outgoing HTTP requests.

MusicBrainz, Deezer and the other public APIs ask a client to say who it is and where to
reach the people behind it. That address is the `project_url` setting (environment
`PROJECT_URL`, Management > Configuration > About). It is empty until someone sets it, and then the
string carries no address at all, so a fresh install never names a project it does not belong to.
"""

from __future__ import annotations

import logging
import os
import threading


def project_url() -> str:
    """The configured project URL, or an empty string when there is none.

    Reads the config store (API value, then environment, then default). When the store
    cannot be opened, as in a bare tool container, the `PROJECT_URL` variable answers.
    """
    try:
        from services.common.config_store import ConfigStore

        value = ConfigStore().get('project_url', '')
    except Exception:
        value = os.getenv('PROJECT_URL', '')
    return str(value or '').strip()


def build_user_agent(product: str, version: str) -> str:
    """Return `"<product>/<version> (+<project_url>)"`, or `"<product>/<version>"` without a URL."""
    agent = f'{product}/{version}'
    url = project_url()
    return f'{agent} (+{url})' if url else agent


_warned = False
_warn_lock = threading.Lock()
_logger = logging.getLogger('music-manager.user-agent')


def _warn_once_without_url() -> None:
    """Log one WARNING per process that requests carry no contact address."""
    global _warned  # pylint: disable=global-statement
    with _warn_lock:
        if _warned:
            return
        _warned = True
    _logger.warning(
        'project_url is empty: requests to MusicBrainz and other public APIs carry no contact address. '
        'Set PROJECT_URL (Management > Configuration > About); MusicBrainz asks clients to identify themselves.'
    )


def user_agent(product: str, version: str) -> str:
    """Build the User-Agent at the moment of the first request, not at import.

    Same string as `build_user_agent`; also logs one WARNING per process when `project_url` is empty.
    Callers call this where they set the header, so importing a module never opens the config store.
    """
    if not project_url():
        _warn_once_without_url()
    return build_user_agent(product, version)
