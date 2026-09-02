"""Steps for features/account_disabled.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up. Without it these
skip.

The account is one the Background provisions, not the admin the Subsonic steps
use. Two reasons. The admin has authenticated against LMS many times by now, and
LMS keeps a granted password for five minutes without asking music-manager again
(SubsonicResource's auth cache) -- so disabling the admin proves nothing for
five minutes, which is longer than the suite. And switching the admin off, even
briefly, would take every later LMS step down with it if this one failed
half-way. A fresh account has neither problem. The provisioning step lives in
conftest.py because account_throttled.feature needs the same one.
"""

from __future__ import annotations

import pytest
import requests
from pytest_bdd import scenarios, then, when

pytestmark = pytest.mark.e2e

scenarios('features/account_disabled.feature')

LOCKED_USER = 'e2e-locked'
TIMEOUT = 10
# Subsonic's code for a bad username or password, which is all a client is told.
SUBSONIC_WRONG_CREDENTIALS = 40


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


def _locked_auth(subsonic_auth: dict, context: dict) -> dict:
    """The locked listener's Subsonic credentials: the admin's, with the account swapped."""
    return {**subsonic_auth, 'u': LOCKED_USER, 'p': context['accounts'][LOCKED_USER]['password']}


@when("the administrator disables the listener's account")
def _disable(manager, api_key, context):
    _set_enabled(manager, api_key, context['accounts'][LOCKED_USER]['id'], False)


@then("music-manager refuses the listener's password")
def _manager_refuses(manager, context):
    # The same call LMS makes on the listener's behalf, made directly. It is a
    # 403 rather than a 401: the password is right, the account is not.
    response = requests.post(
        f'{manager}/api/auth/login',
        json={'username': LOCKED_USER, 'password': context['accounts'][LOCKED_USER]['password']},
        timeout=TIMEOUT,
    )
    assert response.status_code == 403, (
        f'expected 403 for a disabled account, got {response.status_code}: {response.text}'
    )


@then('LMS refuses the listener')
def _lms_refuses(lms, subsonic_auth, context):
    body = _ping(lms, _locked_auth(subsonic_auth, context))
    assert body['status'] == 'failed', 'LMS let in an account music-manager has disabled'
    assert body.get('error', {}).get('code') == SUBSONIC_WRONG_CREDENTIALS, body.get('error')


@when('the administrator enables the account again')
def _enable(manager, api_key, context):
    _set_enabled(manager, api_key, context['accounts'][LOCKED_USER]['id'], True)


@then('LMS lets the listener in')
def _lms_lets_them_in(lms, subsonic_auth, context):
    body = _ping(lms, _locked_auth(subsonic_auth, context))
    assert body['status'] == 'ok', f'LMS still refuses the re-enabled listener: {body.get("error")}'
