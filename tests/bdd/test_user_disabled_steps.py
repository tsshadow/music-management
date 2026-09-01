"""Steps for features/account_disabled.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up. Without it these
skip.

The account is one this feature creates, not the admin the Subsonic steps use.
Two reasons. The admin has authenticated against LMS many times by now, and LMS
keeps a granted password for five minutes without asking music-manager again
(SubsonicResource's auth cache) -- so disabling the admin proves nothing for
five minutes, which is longer than the suite. And switching the admin off, even
briefly, would take every later LMS step down with it if this one failed
half-way. A fresh account has neither problem.
"""

from __future__ import annotations

import pytest
import requests
from pytest_bdd import given, scenarios, then, when

from .conftest import wait_for

pytestmark = pytest.mark.e2e

scenarios('features/account_disabled.feature')

LOCKED_USER = 'e2e-locked'
LOCKED_PASSWORD = 'e2e-locked-password'
TIMEOUT = 10
# Subsonic's code for a bad username or password, which is all a client is told.
SUBSONIC_WRONG_CREDENTIALS = 40


def _users(manager: str, api_key: str) -> list[dict]:
    response = requests.get(f'{manager}/api/users/', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    return response.json()


def _set_enabled(manager: str, api_key: str, user_id: int, enabled: bool) -> None:
    action = 'enable' if enabled else 'disable'
    response = requests.post(f'{manager}/api/users/{user_id}/{action}', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text


def _ping(lms: str, subsonic_auth: dict) -> dict:
    """LMS's answer to the cheapest authenticated request there is.

    A refusal is a 200 with the failure inside it, so the body is what is
    returned and the caller reads the status out of that.
    """
    response = requests.get(f'{lms}/rest/ping.view', params=subsonic_auth, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    return response.json()['subsonic-response']


@pytest.fixture
def locked_auth(subsonic_auth) -> dict:
    """The locked listener's Subsonic credentials: the admin's, with the account swapped."""
    return {**subsonic_auth, 'u': LOCKED_USER, 'p': LOCKED_PASSWORD}


@given('a listener LMS knows but has never let in')
def _known_but_never_in(manager, lms, api_key, subsonic_auth, context):
    existing = next((u for u in _users(manager, api_key) if u.get('username') == LOCKED_USER), None)
    if existing is None:
        created = requests.post(
            f'{manager}/api/users/',
            headers={'x-api-key': api_key},
            json={'username': LOCKED_USER, 'display_name': 'E2E Locked', 'password': LOCKED_PASSWORD},
            timeout=TIMEOUT,
        )
        assert created.status_code == 200, created.text
        context['locked_id'] = created.json()['id']
    else:
        context['locked_id'] = existing['id']

    # Creating a user does not tell LMS; only the first-admin setup does that.
    # This is the same call music-manager makes then, so the account reaches
    # LMS the way a synced one does rather than by a route only this test uses.
    synced = requests.post(f'{lms}/muma/users/sync', headers={'X-API-Key': api_key}, timeout=TIMEOUT)
    assert synced.status_code == 200, synced.text

    # Known, as seen by the admin listing LMS's users -- not by logging in as
    # the listener, which is the one thing this Background must not do: a
    # granted password is remembered for five minutes, and the scenario is
    # about the first time LMS has to ask.
    def listed():
        response = requests.get(f'{lms}/rest/getUsers', params=subsonic_auth, timeout=TIMEOUT)
        assert response.status_code == 200, response.text
        body = response.json()['subsonic-response']
        assert body['status'] == 'ok', f'LMS refused the admin: {body.get("error")}'
        names = [u.get('username') for u in body.get('users', {}).get('user', [])]
        return LOCKED_USER in names or None

    wait_for(f'LMS to learn about {LOCKED_USER}', listed, timeout=60)


@when("the administrator disables the listener's account")
def _disable(manager, api_key, context):
    _set_enabled(manager, api_key, context['locked_id'], False)


@then("music-manager refuses the listener's password")
def _manager_refuses(manager):
    # The same call LMS makes on the listener's behalf, made directly. It is a
    # 403 rather than a 401: the password is right, the account is not.
    response = requests.post(
        f'{manager}/api/auth/login',
        json={'username': LOCKED_USER, 'password': LOCKED_PASSWORD},
        timeout=TIMEOUT,
    )
    assert response.status_code == 403, (
        f'expected 403 for a disabled account, got {response.status_code}: {response.text}'
    )


@then('LMS refuses the listener')
def _lms_refuses(lms, locked_auth):
    body = _ping(lms, locked_auth)
    assert body['status'] == 'failed', 'LMS let in an account music-manager has disabled'
    assert body.get('error', {}).get('code') == SUBSONIC_WRONG_CREDENTIALS, body.get('error')


@when('the administrator enables the account again')
def _enable(manager, api_key, context):
    _set_enabled(manager, api_key, context['locked_id'], True)


@then('LMS lets the listener in')
def _lms_lets_them_in(lms, locked_auth):
    body = _ping(lms, locked_auth)
    assert body['status'] == 'ok', f'LMS still refuses the re-enabled listener: {body.get("error")}'
