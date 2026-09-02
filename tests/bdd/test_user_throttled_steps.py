"""Steps for features/account_throttled.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up. Without it these
skip.

The module name sorts last on purpose. The account it exhausts is its own, so
nothing later would break on it -- but the limit's window is a minute, and a
feature that ran after this against the same account would spend that minute
waiting. Nothing should have to.
"""

from __future__ import annotations

import pytest
import requests
from pytest_bdd import scenarios, then, when

pytestmark = pytest.mark.e2e

scenarios('features/account_throttled.feature')

GUESSER = 'e2e-guesser'
# services/music_manager/rate_limit.py's default: failed attempts per window.
ATTEMPTS_ALLOWED = 10
TIMEOUT = 10
SUBSONIC_WRONG_CREDENTIALS = 40
# LMS reports a throttle as a generic error with a message of its own; the
# code is not distinctive, the message is.
SUBSONIC_THROTTLED_MESSAGE = 'throttled'


def _ping(lms: str, auth: dict) -> dict:
    response = requests.get(f'{lms}/rest/ping.view', params=auth, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    return response.json()['subsonic-response']


def _as_guesser(subsonic_auth: dict, password: str) -> dict:
    return {**subsonic_auth, 'u': GUESSER, 'p': password}


@when("the listener's password is guessed wrong ten times over the Subsonic API")
def _guess_wrong_ten_times(lms, subsonic_auth, context):
    # Sequential on purpose: the limit is a sliding window and the count has to
    # be unambiguous, so no request may overlap another.
    context['guesses'] = [
        _ping(lms, _as_guesser(subsonic_auth, f'not-the-password-{attempt}')) for attempt in range(ATTEMPTS_ALLOWED)
    ]


@then('each guess was refused as a wrong password')
def _each_guess_refused(context):
    # Refused as wrong, not as throttled: the limit must not fire early, or a
    # listener who mistypes twice would be locked out as if under attack.
    for attempt, body in enumerate(context['guesses'], start=1):
        assert body['status'] == 'failed', f'guess {attempt} was accepted'
        assert body.get('error', {}).get('code') == SUBSONIC_WRONG_CREDENTIALS, (
            f'guess {attempt} was refused for another reason than a wrong password: {body.get("error")}'
        )


@when('the listener tries once more with the right password')
def _try_the_right_password(lms, subsonic_auth, context):
    context['final'] = _ping(lms, _as_guesser(subsonic_auth, context['accounts'][GUESSER]['password']))


@then('LMS reports the listener as throttled')
def _lms_reports_throttled(context):
    body = context['final']
    assert body['status'] == 'failed', 'the right password got in while the account was over its limit'
    error = body.get('error', {})
    assert SUBSONIC_THROTTLED_MESSAGE in str(error.get('message', '')).lower(), (
        f'refused, but not as a throttle: {error}. A wrong-password code here would mean LMS '
        f'turned the 429 into a 401, and a client would keep retrying'
    )


@then("the admin's own requests still go through")
def _admin_unaffected(lms, subsonic_auth):
    # Same caller address as every guess above -- LMS makes them all -- so this
    # holds only because the bucket is the account, not the address.
    body = _ping(lms, subsonic_auth)
    assert body['status'] == 'ok', (
        f'the admin was locked out by someone else\'s guesses: {body.get("error")} -- the rate limit is '
        f'keyed on the caller again instead of on the account'
    )
