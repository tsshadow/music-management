"""Steps for features/scan_to_listen.feature.

The feature file is the description of this chain; this is only what the steps
do. If the two disagree, the feature file is the one that is right and this is
the bug -- that is the whole reason the chain is written there rather than in a
docstring here. It replaced a plain pytest function that said the same thing,
which was deleted rather than kept alongside.

Started by scripts/test/core-e2e.sh, which brings the stack up and puts the
fixture in place. Without it these skip.
"""
from __future__ import annotations

import time

import pytest
import requests
from pytest_bdd import given, scenarios, then, when

pytestmark = pytest.mark.e2e

scenarios('features/scan_to_listen.feature')

# The fixture's file name and the title inside it are two different strings, and
# the library is keyed on the tag, not on the path: the scanner stores TIT2 as
# library_tracks.title, and /api/library/tracks searches title, artist and label.
# Searching for the file name therefore matches nothing however well the scan
# went, so these are kept apart deliberately.
TRACK_FILE = 'ci-test-track-001.mp3'
TRACK_TITLE = 'CI Test Track'
# Who the listen belongs to, in music-manager's own records. Not the LMS account
# the Subsonic steps authenticate as -- that one is created by the stack script
# and reaches the suite as the subsonic_auth fixture.
USERNAME = 'e2e'
TIMEOUT = 10


def _wait_for(description: str, predicate, timeout: int = 120):
    """Poll until true, and say what was being waited for when it never is.

    A bare timeout in an end-to-end test is the least useful failure there is:
    the whole point is that any of six components could be the one that did not
    do its part.
    """
    deadline = time.time() + timeout
    last = None
    while time.time() < deadline:
        last = predicate()
        if last:
            return last
        time.sleep(2)
    pytest.fail(f'timed out after {timeout}s waiting for: {description} (last result: {last!r})')


# --- Given -------------------------------------------------------------------
# Both background steps are the stack that scripts/test/core-e2e.sh brought up
# before pytest started. They assert rather than act: a Given that silently did
# nothing would let the whole scenario pass against no stack at all.


@given('the test stack is running')
def _stack_is_running(manager, api_key):
    response = requests.get(f'{manager}/health', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, (
        f'music-manager is not answering on {manager}: {response.status_code} {response.text}'
    )


@given('the fixture track is on the music volume')
def _fixture_is_in_place():
    # The file is inside the LMS container, not on this filesystem, so there is
    # nothing to stat here. The scan step below is what proves it arrived, and
    # it fails with a named timeout rather than an AssertionError if it did not.
    pass


@given('LMS has scanned its library')
def _lms_has_scanned(lms, subsonic_auth):
    # e2e_stack_scan_lms already waited for the track to appear, so this asserts
    # the state it left behind rather than waiting again: authentication works,
    # and no scan is still in flight that could make the search below flap.
    response = requests.get(f'{lms}/rest/getScanStatus.view', params=subsonic_auth, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    body = response.json()['subsonic-response']
    assert body['status'] == 'ok', f'LMS refused the request: {body.get("error")}'
    assert body['scanStatus']['scanning'] is False, 'LMS is still scanning'


# --- When / Then -------------------------------------------------------------


@when('the scanner is asked to scan the library')
def _scan(manager, api_key):
    # The scan runs as a background task, so a 200 only means it was accepted;
    # 409 means one was already running, which is equally fine. Anything else is
    # worth failing on straight away rather than polling for two minutes for a
    # scan that never started.
    started = requests.post(
        f'{manager}/api/scanner/scan/all',
        headers={'x-api-key': api_key},
        timeout=TIMEOUT,
    )
    assert started.status_code in (200, 409), started.text


@then('the track is in the library under its own file name')
def _track_is_in_the_library(manager, api_key, context):
    def scanned():
        response = requests.get(
            f'{manager}/api/library/tracks',
            headers={'x-api-key': api_key},
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
    context['track'] = track


@when('the mobile app searches for the track over the Subsonic API')
def _subsonic_search(lms, subsonic_auth, context):
    context['search'] = requests.get(
        f'{lms}/rest/search3',
        params={'query': TRACK_TITLE, **subsonic_auth},
        timeout=TIMEOUT,
    )


@then('the Subsonic search returns the track')
def _subsonic_search_returns_the_track(context):
    search = context['search']
    assert search.status_code == 200, search.text

    # Subsonic puts failures inside a 200, so the status has to be read out of
    # the body. This step asserted only on the HTTP code until the fixture step
    # learned to create a user and scan: it was passing on
    # {"status":"failed","error":{"code":40,"message":"Wrong username or
    # password."}} and proving nothing about LMS beyond that it was listening.
    body = search.json()['subsonic-response']
    assert body['status'] == 'ok', f'LMS refused the search: {body.get("error")}'

    songs = body.get('searchResult3', {}).get('song', [])
    titles = [song.get('title') for song in songs]
    assert TRACK_TITLE in titles, (
        f'LMS answered but does not have the fixture track; it returned {titles!r}'
    )


@when('a listen is recorded for the track')
def _scrobble(manager, api_key, context):
    track = context['track']
    context['scrobble'] = requests.post(
        f'{manager}/api/scrobble/event',
        headers={'x-api-key': api_key},
        json={
            'artist_name': track.get('artist') or 'Unknown Artist',
            'track_title': track['title'],
            'username': USERNAME,
            'source': 'e2e',
        },
        timeout=TIMEOUT,
    )


@then('the listen is matched to the track that was scanned')
def _listen_is_matched(context):
    scrobble = context['scrobble']
    assert scrobble.status_code == 200, scrobble.text
    assert scrobble.json().get('matched') is True, (
        'the listen did not match a track: the scan and the scrobble disagree about its name'
    )
