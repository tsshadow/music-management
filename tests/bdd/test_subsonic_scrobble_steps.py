"""Steps for features/subsonic_scrobble.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up. Without it these
skip.

Runs after scan_to_listen, by conftest.FEATURE_ORDER: that feature pins
music-manager's listen counter at zero in its Background, and this one moves it.
"""

from __future__ import annotations

import pytest
import requests
from pytest_bdd import given, scenarios, then, when

from .conftest import TRACK_TITLE, stats, wait_for

pytestmark = pytest.mark.e2e

scenarios('features/subsonic_scrobble.feature')

TIMEOUT = 10


def _song(lms: str, subsonic_auth: dict) -> dict:
    """LMS's own row for the fixture track, which is what a client scrobbles by."""
    response = requests.get(f'{lms}/rest/search3', params={'query': TRACK_TITLE, **subsonic_auth}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    body = response.json()['subsonic-response']
    assert body['status'] == 'ok', f'LMS refused the search: {body.get("error")}'
    songs = body.get('searchResult3', {}).get('song', [])
    song = next((s for s in songs if s.get('title') == TRACK_TITLE), None)
    assert song is not None, f'LMS does not have the fixture track; it returned {songs!r}'
    return song


@given('the number of listens on record is known')
def _count_listens(manager, api_key, context):
    # A baseline rather than an assertion of zero: scan_to_listen.feature has
    # already recorded a listen by the time this runs, and this scenario is about
    # the hop, not about the table starting empty.
    before = stats(manager, api_key)
    context['listens_before'] = before.get('total_scrobbles', 0)
    context['unmatched_before'] = before.get('total_unmatched', 0)


@when('the mobile app submits the play over the Subsonic API')
def _scrobble_over_subsonic(lms, subsonic_auth, context):
    song = _song(lms, subsonic_auth)
    # submission=true is a finished play. Without it LMS reports "now playing",
    # which its relay deliberately drops -- music-manager cannot tell a started
    # track from a listened one, and forwarding starts once counted every skip.
    context['submission'] = requests.get(
        f'{lms}/rest/scrobble',
        params={'id': song['id'], 'submission': 'true', 'source': 'e2e-mobile', **subsonic_auth},
        timeout=TIMEOUT,
    )


@then('LMS accepts the submission')
def _lms_accepted_it(context):
    submission = context['submission']
    assert submission.status_code == 200, submission.text
    body = submission.json()['subsonic-response']
    assert body['status'] == 'ok', f'LMS refused the scrobble: {body.get("error")}'


@then('music-manager has recorded one more listen')
def _one_more_listen(manager, api_key, context):
    # LMS answers the client before it has relayed anything: the post to
    # music-manager goes out on its own thread, so this polls. The window is
    # short because the relay is a single HTTP call on the same network; a listen
    # that needs longer than this is one that got queued, which is the failure
    # the feature file describes.
    expected = context['listens_before'] + 1

    def relayed():
        count = stats(manager, api_key).get('total_scrobbles', 0)
        return count if count >= expected else None

    count = wait_for('LMS to relay the play to music-manager', relayed, timeout=30)
    assert count == expected, (
        f'expected the listen count to go from {context["listens_before"]} to {expected}, it is {count}'
    )


@then('none of it was filed as unmatched')
def _nothing_unmatched(manager, api_key, context):
    after = stats(manager, api_key).get('total_unmatched', 0)
    assert after == context['unmatched_before'], (
        f'unmatched listens went from {context["unmatched_before"]} to {after}: LMS relayed the play '
        f'under a name music-manager could not match to the track it scanned'
    )
