"""The one place that builds the User-Agent string for outgoing HTTP requests.

MusicBrainz, Deezer and the other public APIs ask a client to say who it is and where to
reach the people behind it. That address is the `project_url` setting (environment
`PROJECT_URL`, Beheer > Config > About). It is empty until someone sets it, and then the
string carries no address at all, so a fresh install never names a project it does not belong to.
"""

from __future__ import annotations

import os


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
