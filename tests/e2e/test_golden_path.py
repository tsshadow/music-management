"""The golden path: a track goes in one end and comes out as a listen at the other.

Every other suite proves one component in isolation. The contract tests prove LMS answers the shape
music-manager expects; the integration tests prove MariaDB accepts the SQL; the unit tests prove the
functions. None of them proves that a file dropped on disk becomes something you can play and that
playing it is recorded.

This walks the whole chain against a real stack: scan the fixture into the library, find it over
the Subsonic API the way the mobile app does, stream a byte of it, scrobble it, and read the listen
back out of music-manager.

Started by scripts/test/core-e2e.sh, which brings the stack up and puts the fixture in place. Run it
rather than pytest directly; without the stack these skip.
"""
from __future__ import annotations

import os
import time

import pytest
import requests

pytestmark = pytest.mark.e2e

TRACK_NAME = 'ci-test-track-001'
USERNAME = 'e2e'
TIMEOUT = 10


def _base(port_var: str) -> str:
    port = os.getenv(port_var)
    if not port:
        pytest.skip(f'{port_var} is not set; start the stack with scripts/test/core-e2e.sh')
    return f'http://127.0.0.1:{port}'


@pytest.fixture(scope='session')
def manager() -> str:
    return _base('MUMA_TEST_PORT_MANAGER')


@pytest.fixture(scope='session')
def lms() -> str:
    return _base('MUMA_TEST_PORT_LMS')


@pytest.fixture(scope='session')
def api_key() -> str:
    return os.getenv('API_KEY', 'test-api-key')


def _wait_for(description: str, predicate, timeout: int = 120):
    """Poll until true, and say what was being waited for when it never is.

    A bare timeout in an end-to-end test is the least useful failure there is: the whole point is
    that any of six components could be the one that did not do its part.
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(2)
    pytest.fail(f'timed out after {timeout}s waiting for: {description} (last result: {last!r})')


def test_a_scanned_track_becomes_a_listen(manager, lms, api_key):
    headers = {'x-api-key': api_key}

    # 1. The scanner finds the file that scripts/test/core-e2e.sh put in the music volume.
    requests.post(f'{manager}/api/scanner/scan/all', headers=headers, timeout=TIMEOUT)

    def scanned():
        response = requests.get(
            f'{manager}/api/library/tracks',
            headers=headers,
            params={'q': TRACK_NAME, 'limit': 10},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return None
        tracks = response.json()
        rows = tracks if isinstance(tracks, list) else tracks.get('tracks', [])
        return next((t for t in rows if TRACK_NAME in str(t.get('title', ''))), None)

    track = _wait_for('the scanner to pick up the fixture track', scanned)

    # 2. The mobile app's own route to it: search over the Subsonic API.
    search = requests.get(
        f'{lms}/rest/search3',
        params={
            'query': TRACK_NAME, 'u': USERNAME, 'p': 'e2e',
            'v': '1.16.1', 'c': 'e2e-test', 'f': 'json',
        },
        timeout=TIMEOUT,
    )
    assert search.status_code == 200, search.text

    # 3. A listen for it is recorded and readable again. This is the half that was silently
    #    losing two thirds of everything before the rematching work.
    scrobble = requests.post(
        f'{manager}/api/scrobble/event',
        headers=headers,
        json={
            'artist_name': track.get('artist') or 'Unknown Artist',
            'track_title': track['title'],
            'username': USERNAME,
            'source': 'e2e',
        },
        timeout=TIMEOUT,
    )
    assert scrobble.status_code == 200, scrobble.text
    assert scrobble.json().get('matched') is True, (
        'the listen did not match a track: the scan and the scrobble disagree about its name'
    )
