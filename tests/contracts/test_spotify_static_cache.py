"""
Cache headers on the web UI LMS serves from its "spotify" docroot (issue #114).

The bundle is split into chunks with content hashes in their names, so the two kinds of file
need opposite treatment: a hashed file under /assets/ never changes and may be cached for a
year, while index.html -- and every SPA route that falls back to it -- names the current build's
chunks and must be revalidated on every load, or a browser keeps starting a build whose chunks
the last deploy replaced.

Like the other contract tests this assumes `docker/compose.test.yml` is running (see
scripts/test/contracts.sh). The LMS image there is built from Dockerfile-release, which copies
the built frontend into the docroot, so this exercises the real SpotifyResource.
"""

import os
import re

import pytest
import requests

LMS_PORT = os.environ.get("MUMA_TEST_PORT_LMS", "15082")
LMS_URL = f"http://localhost:{LMS_PORT}"

LONG_CACHE = "public, max-age=31536000, immutable"


@pytest.fixture(scope="module", name="ui_base")
def fixture_ui_base():
    """Where SpotifyResource is mounted: "/" normally, "/spotify" when "/" was taken."""
    for base in ("", "/spotify"):
        response = requests.get(f"{LMS_URL}{base}/", timeout=10)
        if response.ok and 'id="boot-screen"' in response.text:
            return base
    pytest.fail("LMS serves no web UI at / or /spotify/")


def test_index_html_is_revalidated_on_every_load(ui_base):
    response = requests.get(f"{LMS_URL}{ui_base}/", timeout=10)

    assert response.headers.get("Cache-Control") == "no-cache"


def test_spa_route_fallback_is_revalidated_too(ui_base):
    response = requests.get(f"{LMS_URL}{ui_base}/management/config", timeout=10)

    assert response.ok
    assert 'id="boot-screen"' in response.text
    assert response.headers.get("Cache-Control") == "no-cache"


def test_hashed_chunks_are_cached_for_a_year(ui_base):
    index = requests.get(f"{LMS_URL}{ui_base}/", timeout=10).text
    entry = re.search(r'src="(?:/spotify)?/(assets/[^"]+\.js)"', index)
    assert entry, "index.html names no entry chunk under /assets/"

    response = requests.get(f"{LMS_URL}{ui_base}/{entry.group(1)}", timeout=10)

    assert response.ok
    assert response.headers.get("Content-Type", "").startswith("text/javascript")
    assert response.headers.get("Cache-Control") == LONG_CACHE


def test_unhashed_files_are_not_long_cached(ui_base):
    # version.json names the build a diagnostics report came from; it changes on every deploy
    # under the same name.
    response = requests.get(f"{LMS_URL}{ui_base}/version.json", timeout=10)

    assert response.ok
    assert response.headers.get("Cache-Control") == "no-cache"
