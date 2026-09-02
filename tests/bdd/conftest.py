"""Fixtures and shared steps for the Gherkin walk of the server chain.

Ports rather than hostnames because the stack publishes on the host and both are
picked free at runtime; scripts/test/core-e2e.sh is what exports them. Skipping
rather than failing when they are unset is deliberate: a bare `pytest tests/bdd`
with no stack up should say so, not report a broken chain.

Steps live here when more than one feature uses them. pytest-bdd resolves step
definitions from conftest.py as well as from the module next to the feature, so
this is where a Given shared by two features belongs -- copying it into both is
how the two slowly stop meaning the same thing.
"""

from __future__ import annotations

import os
import time

import pytest
import requests
from pytest_bdd import given, parsers, when

TIMEOUT = 10

# The order the features run in, and it matters: several assert the state an
# earlier one leaves behind, or pin a counter at zero that a later one moves.
# pytest would otherwise run the modules in name order, which held for as long
# as every new feature happened to sort behind the one it depended on -- and
# stopped holding the moment one had to run last for a reason its name could
# not carry. The rules, in run order:
#
#   genre_curation   asserts no scan has happened yet, so it goes first
#   genre_decision   needs the scan genre_curation triggered, keeps the genre
#   playlist_unrated needs a scanned library
#   rating_roundtrip rates the fixture as the admin
#   scan_to_listen   pins the listen counter at zero, then moves it
#   subsonic_scrobble moves it again
#   unmatched_listen pins the *unmatched* counter at zero
#   user_disabled / user_throttled act on accounts of their own
#   genre_rejected   rewrites the fixture's bytes, so nothing may stream after it
#
# A module not listed here runs after all of these, in name order, which is
# the safe default for a feature that touches nothing shared.
FEATURE_ORDER = [
    'test_access_control_steps',
    'test_genre_curation_steps',
    'test_genre_decision_steps',
    'test_playlist_unrated_steps',
    'test_rating_roundtrip_steps',
    'test_scan_to_listen_steps',
    'test_subsonic_scrobble_steps',
    'test_unmatched_listen_steps',
    'test_user_disabled_steps',
    'test_user_throttled_steps',
    'test_genre_rejected_steps',
]


def pytest_collection_modifyitems(items):
    """Run the feature modules in FEATURE_ORDER, not in name order."""

    def rank(item):
        name = item.module.__name__.rsplit('.', 1)[-1]
        position = FEATURE_ORDER.index(name) if name in FEATURE_ORDER else len(FEATURE_ORDER)
        return (position, name)

    items.sort(key=rank)


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
    return os.getenv('API_KEY') or 'test-api-key'


@pytest.fixture(scope='session')
def subsonic_auth() -> dict:
    """Credentials for LMS, which has no users of its own.

    music-manager owns the accounts and pushes them across; the one used here is
    created by e2e_stack_scan_lms before pytest starts. Subsonic reports a bad
    password inside a 200, so a wrong value here does not fail loudly -- it
    quietly turns every LMS assertion into a check that the process is listening.
    """
    return {
        'u': os.getenv('MUMA_TEST_LMS_USER') or 'e2e-admin',
        'p': os.getenv('MUMA_TEST_LMS_PASSWORD') or 'e2e-password',
        'v': '1.16.1',
        'c': 'e2e-test',
        'f': 'json',
    }


@pytest.fixture
def context() -> dict:
    """What one step hands to the next.

    Gherkin steps are functions with no return value to pass around, so the
    thing under test has to live somewhere both can reach. Function-scoped, so a
    second scenario never inherits the first one's track.
    """
    return {}


TRACK_FILE = 'ci-test-track-001.mp3'
TRACK_TITLE = 'CI Test Track'
# The genre in the fixture's tag, per tests/fixtures/expected/ci-test-track-001.json.
FIXTURE_GENRE = 'Electronic'


def wait_for(description: str, predicate, timeout: int = 120):
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
    return None


def request_scan(manager: str, api_key: str) -> None:
    """Ask music-manager to walk the music volume.

    The scan is a background task, so a 200 only means it was accepted and 409
    means one is already running -- which is what a second feature asking for a
    scan looks like. Anything else fails immediately rather than spending two
    minutes polling for a scan that never started.
    """
    started = requests.post(
        f'{manager}/api/scanner/scan/all',
        headers={'x-api-key': api_key},
        timeout=TIMEOUT,
    )
    assert started.status_code in (200, 409), started.text


def wait_for_fixture_track(manager: str, api_key: str) -> dict:
    """music-manager's own row for the fixture track, once the scan has found it."""

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

    return wait_for('the scanner to pick up the fixture track', scanned)


def scan_and_wait_for_the_fixture(manager: str, api_key: str) -> dict:
    """Both halves, for a feature that needs a scanned library as a precondition
    rather than as the thing it is testing -- the rating webhook looks its track
    up by path, and cannot link anything to a library that is empty."""
    request_scan(manager, api_key)
    return wait_for_fixture_track(manager, api_key)


def stats(manager: str, api_key: str) -> dict:
    """music-manager's own counters, which is the only way back to what it kept.

    Neither listen table has an endpoint that serves rows: `scrobble_listens` and
    `scrobble_unmatched_listens` are written by the scrobble endpoint and read
    here and by the rematcher, and by nothing else. So a feature can assert that
    a listen was stored, and cannot assert which one -- the counters are the
    whole surface.
    """
    response = requests.get(f'{manager}/api/stats/', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    return response.json()


def curation_queue(manager: str, api_key: str) -> list[dict]:
    """Genres awaiting a decision.

    A different view than /api/library/genres: that one inner-joins the
    per-track table, so a genre nothing has been attached to yet is invisible
    there however correctly it was registered.
    """
    response = requests.get(
        f'{manager}/api/rules/genres',
        headers={'x-api-key': api_key},
        params={'state': 'unknown'},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    return body if isinstance(body, list) else body.get('genres', [])


@given('the test stack is running')
def _stack_is_running(manager, api_key):
    """Shared by every feature: nothing below means anything without it.

    It asserts rather than does nothing, because a Given that quietly passes lets
    a whole scenario run green against a stack that never came up.
    """
    response = requests.get(f'{manager}/health', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, (
        f'music-manager is not answering on {manager}: {response.status_code} {response.text}'
    )


@given('LMS has scanned its library')
def _lms_has_scanned(lms, subsonic_auth):
    """e2e_stack_scan_lms already waited for the track, so this asserts the state
    it left behind rather than waiting again: authentication works, and no scan
    is still in flight that could make a search flap."""
    response = requests.get(f'{lms}/rest/getScanStatus.view', params=subsonic_auth, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    body = response.json()['subsonic-response']
    assert body['status'] == 'ok', f'LMS refused the request: {body.get("error")}'
    assert body['scanStatus']['scanning'] is False, 'LMS is still scanning'


@given('the fixture track is on the music volume')
def _fixture_is_in_place():
    """The one step here that asserts nothing, and says why.

    The file is inside the LMS container rather than on this filesystem, so
    there is nothing to stat. What proves it arrived is the scan that follows,
    which fails with a named timeout rather than an anonymous one.
    """


@when('the scanner is asked to scan the library')
def _scan(manager, api_key):
    """Shared: two features act on the scan rather than assuming it."""
    request_scan(manager, api_key)


@given('music-manager has scanned the fixture track')
def _manager_has_scanned(manager, api_key, context):
    """A precondition for features that are not testing the scan itself.

    Cheap on a second call: the scan endpoint answers 409 while one is running,
    and the track is already there once any feature has triggered it.
    """
    context['track'] = scan_and_wait_for_the_fixture(manager, api_key)


@given("the fixture's genre is waiting for a decision")
def _genre_is_queued(manager, api_key):
    """Shared: the state the tagger step in scripts/lib/e2e-stack.sh leaves
    behind, which one feature scans into and the next decides on."""
    queued = [row.get('name') for row in curation_queue(manager, api_key)]
    assert FIXTURE_GENRE in queued, (
        f'{FIXTURE_GENRE} is not in the curation queue: {queued!r} -- the tagger step in '
        f'scripts/lib/e2e-stack.sh is what puts it there, and nothing else does'
    )


def provision_lms_account(manager, lms, api_key, subsonic_auth, username, password, context) -> int:
    """An account music-manager owns and LMS has been told about, without ever
    logging in as it.

    Creating a user does not tell LMS; only the first-admin setup does. So the
    account is pushed across with the same call music-manager makes then, and
    "LMS knows it" is read from the admin's user listing rather than by
    authenticating as the new account -- LMS remembers a granted password for
    five minutes, and the features that use this need the first password they
    present to be the first one LMS has to ask music-manager about.
    """
    users = requests.get(f'{manager}/api/users/', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert users.status_code == 200, users.text
    existing = next((u for u in users.json() if u.get('username') == username), None)
    if existing is None:
        created = requests.post(
            f'{manager}/api/users/',
            headers={'x-api-key': api_key},
            json={'username': username, 'display_name': username, 'password': password},
            timeout=TIMEOUT,
        )
        assert created.status_code == 200, created.text
        user_id = created.json()['id']
    else:
        user_id = existing['id']

    synced = requests.post(f'{lms}/muma/users/sync', headers={'X-API-Key': api_key}, timeout=TIMEOUT)
    assert synced.status_code == 200, synced.text

    def listed():
        response = requests.get(f'{lms}/rest/getUsers', params=subsonic_auth, timeout=TIMEOUT)
        assert response.status_code == 200, response.text
        body = response.json()['subsonic-response']
        assert body['status'] == 'ok', f'LMS refused the admin: {body.get("error")}'
        names = [u.get('username') for u in body.get('users', {}).get('user', [])]
        return username in names or None

    wait_for(f'LMS to learn about {username}', listed, timeout=60)
    context.setdefault('accounts', {})[username] = {'id': user_id, 'password': password}
    return user_id


@given(parsers.parse('a listener "{username}" LMS knows but has never let in'))
def _known_but_never_in(manager, lms, api_key, subsonic_auth, context, username):
    """Shared by the features that test what LMS does with an account's standing."""
    provision_lms_account(manager, lms, api_key, subsonic_auth, username, f'{username}-password', context)
