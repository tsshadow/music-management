"""Steps for features/unmatched_listen.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up. Without it these
skip.
"""
from __future__ import annotations

import uuid

import pytest
import requests
from pytest_bdd import given, scenarios, then, when

from .conftest import stats

pytestmark = pytest.mark.e2e

scenarios('features/unmatched_listen.feature')

USERNAME = 'e2e'
TIMEOUT = 10


def _unmatched_count(manager: str, api_key: str) -> int:
    return stats(manager, api_key).get('total_unmatched', 0)


@given('no unmatched listens have been recorded yet')
def _no_unmatched_yet(manager, api_key, context):
    # A different counter than the one scan_to_listen.feature pins at zero, which
    # is what lets these two run against the same stack in either order. Add a
    # scenario that scrobbles a track the library *does* have, and it belongs in
    # that feature rather than this one, or both baselines stop holding.
    context['unmatched_before'] = _unmatched_count(manager, api_key)
    assert context['unmatched_before'] == 0, (
        f'the stack came up with {context["unmatched_before"]} unmatched listens'
    )


@when('a listen is recorded for a track the library does not have')
def _scrobble_something_unknown(manager, api_key, context):
    # A fresh title every run. The table has a unique key over
    # (artist, title, listened_at, username), and a fixed title would collide
    # with itself on a re-run against a stack that was not torn down -- the
    # insert would be swallowed by ON DUPLICATE KEY and the count would not move,
    # which reads exactly like the listen being dropped.
    context['unknown_title'] = f'Nothing By This Name {uuid.uuid4().hex[:8]}'
    context['scrobble'] = requests.post(
        f'{manager}/api/scrobble/event',
        headers={'x-api-key': api_key},
        json={
            'artist_name': 'No Such Artist',
            'track_title': context['unknown_title'],
            'username': USERNAME,
            'source': 'e2e',
        },
        timeout=TIMEOUT,
    )


@then('the listen is not reported as a match')
def _not_reported_as_a_match(context):
    scrobble = context['scrobble']
    assert scrobble.status_code == 200, scrobble.text
    assert scrobble.json().get('matched') is False, (
        'a title that is not in the library was reported as matched, which means '
        'the matcher linked this listen to some other track'
    )


@then('it is kept for re-matching later')
def _kept_for_rematching(manager, api_key, context):
    after = _unmatched_count(manager, api_key)
    assert after == context['unmatched_before'] + 1, (
        f'unmatched listens went from {context["unmatched_before"]} to {after}: '
        f'the listen was answered but not kept'
    )
