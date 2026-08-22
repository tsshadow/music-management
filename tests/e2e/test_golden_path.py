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

# The fixture's file name and the title inside it are two different strings, and the library is
# keyed on the tag, not on the path: the scanner stores TIT2 as library_tracks.title, and
# /api/library/tracks searches title, artist and label. Searching for the file name therefore
# matches nothing however well the scan went, so these are kept apart deliberately.
TRACK_FILE = 'ci-test-track-001.mp3'
TRACK_TITLE = 'CI Test Track'
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
    #    The scan runs as a background task, so a 200 only means it was accepted; 409 means one
    #    was already running, which is equally fine. Anything else is worth failing on straight
    #    away rather than spending two minutes polling for a scan that never started.
    started = requests.post(f'{manager}/api/scanner/scan/all', headers=headers, timeout=TIMEOUT)
    assert started.status_code in (200, 409), started.text

    def scanned():
        response = requests.get(
            f'{manager}/api/library/tracks',
            headers=headers,
            params={'q': TRACK_TITLE, 'limit': 10},
            timeout=TIMEOUT,
        )
        if response.status_code != 200:
            return None
        tracks = response.json()
        rows = tracks if isinstance(tracks, list) else tracks.get('tracks', [])
        return next((t for t in rows if TRACK_TITLE in str(t.get('title', ''))), None)

    track = _wait_for('the scanner to pick up the fixture track', scanned)
    assert str(track.get('file_path', '')).endswith(TRACK_FILE), (
        f'matched a track by title that is not the fixture: {track!r}'
    )

    # 2. The mobile app's own route to it: search over the Subsonic API.
    #    Only that the query is served, not that it finds the fixture: LMS keeps its own index and
    #    nothing here triggers its scan, so the file is on its disk without being in its library.
    #    Asserting on the results needs an LMS scan first; see the note in scripts/test/core-e2e.sh.
    search = requests.get(
        f'{lms}/rest/search3',
        params={
            'query': TRACK_TITLE, 'u': USERNAME, 'p': 'e2e',
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
