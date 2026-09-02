"""Steps for features/account_disabled.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up. Without it these
skip.

Both scenarios act on an account their own Background provisions, never on the
admin the Subsonic steps use: switching the admin off, even briefly, would take
every later LMS step down with it if the scenario failed half-way. "The
listener" in a step is whichever account the provisioning step in conftest.py
created last; the second scenario is the one that first lets that account in,
so that LMS has a cached grant to forget.
"""

from __future__ import annotations

import pytest
import requests
from pytest_bdd import given, scenarios, then, when

pytestmark = pytest.mark.e2e

scenarios('features/account_disabled.feature')

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


def _listener(context: dict) -> dict:
    """The account the Background provisioned: its name, id and password."""
    name = context['listener']
    return {'username': name, **context['accounts'][name]}


def _listener_auth(subsonic_auth: dict, context: dict) -> dict:
    """The listener's Subsonic credentials: the admin's, with the account swapped."""
    listener = _listener(context)
    return {**subsonic_auth, 'u': listener['username'], 'p': listener['password']}


@given('LMS has let the listener in')
def _lms_has_let_them_in(lms, subsonic_auth, context):
    # The point of this Given is the side effect: a granted password now sits in
    # LMS's cache with its full window ahead of it.
    body = _ping(lms, _listener_auth(subsonic_auth, context))
    assert body['status'] == 'ok', f'LMS refused the listener before anything was done to them: {body.get("error")}'


@when("the administrator disables the listener's account")
def _disable(manager, api_key, context):
    _set_enabled(manager, api_key, _listener(context)['id'], False)


@then("music-manager refuses the listener's password")
def _manager_refuses(manager, context):
    # The same call LMS makes on the listener's behalf, made directly. It is a
    # 403 rather than a 401: the password is right, the account is not.
    listener = _listener(context)
    response = requests.post(
        f'{manager}/api/auth/login',
        json={'username': listener['username'], 'password': listener['password']},
        timeout=TIMEOUT,
    )
    assert response.status_code == 403, (
        f'expected 403 for a disabled account, got {response.status_code}: {response.text}'
    )


@then('LMS refuses the listener')
def _lms_refuses(lms, subsonic_auth, context):
    # No polling, in either scenario. The first has no cached grant to get in
    # the way; the second relies on the disable having emptied LMS's cache
    # before music-manager answered, so a refusal that needed waiting for would
    # be the five-minute window showing through again.
    body = _ping(lms, _listener_auth(subsonic_auth, context))
    assert body['status'] == 'failed', 'LMS let in an account music-manager has disabled'
    assert body.get('error', {}).get('code') == SUBSONIC_WRONG_CREDENTIALS, body.get('error')


@when('the administrator enables the account again')
def _enable(manager, api_key, context):
    _set_enabled(manager, api_key, _listener(context)['id'], True)


@then('LMS lets the listener in')
def _lms_lets_them_in(lms, subsonic_auth, context):
    body = _ping(lms, _listener_auth(subsonic_auth, context))
    assert body['status'] == 'ok', f'LMS still refuses the re-enabled listener: {body.get("error")}'
