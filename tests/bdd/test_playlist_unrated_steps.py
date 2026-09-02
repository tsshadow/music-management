"""Steps for features/dynamic_playlist.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up. Without it these
skip.

The listener is a second account rather than the one the Subsonic steps use.
Ratings are per username, and rating_roundtrip.feature stars the fixture as the
admin -- so as the admin the track is rated by the time this runs, and "unrated
tracks are offered" would be satisfied by a filter that dropped them. A fresh
account has no ratings whichever order the features run in.
"""

from __future__ import annotations

import pytest
import requests
from pytest_bdd import given, scenarios, then, when

from .conftest import TRACK_FILE, TRACK_TITLE

pytestmark = pytest.mark.e2e

scenarios('features/dynamic_playlist.feature')

LISTENER = 'e2e-listener'
# The seeded playlist whose only filter is the rating range; the others each
# name a genre the fixture does not carry.
UNFILTERED_PLAYLIST = 'Recently Added'
TIMEOUT = 10


def _users(manager: str, api_key: str) -> list[dict]:
    response = requests.get(f'{manager}/api/users/', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    return response.json()


@given('a listener who has never rated anything')
def _fresh_listener(manager, api_key, context):
    existing = next((u for u in _users(manager, api_key) if u.get('username') == LISTENER), None)
    if existing is None:
        created = requests.post(
            f'{manager}/api/users/',
            headers={'x-api-key': api_key},
            json={'username': LISTENER, 'display_name': 'E2E Listener'},
            timeout=TIMEOUT,
        )
        assert created.status_code == 200, created.text
        context['listener_id'] = created.json()['id']
    else:
        # A re-run against a stack that was not torn down. Reusing the account
        # is safe only because nothing in this suite rates as this listener.
        context['listener_id'] = existing['id']

    ratings = requests.get(f'{manager}/api/rating/ratings/{LISTENER}', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert ratings.status_code == 200, ratings.text
    assert ratings.json() == [], f'the listener has rated something already: {ratings.json()!r}'


@when("the listener's default playlists are seeded")
def _seed(manager, api_key, context):
    response = requests.post(
        f'{manager}/api/users/{context["listener_id"]}/dynamic-playlists/seed-defaults',
        headers={'x-api-key': api_key},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text


@when('the listener opens the playlist that filters on nothing')
def _open_unfiltered(manager, api_key, context):
    listed = requests.get(
        f'{manager}/api/users/{context["listener_id"]}/dynamic-playlists',
        headers={'x-api-key': api_key},
        timeout=TIMEOUT,
    )
    assert listed.status_code == 200, listed.text
    playlist = next((p for p in listed.json() if p.get('name') == UNFILTERED_PLAYLIST), None)
    assert playlist is not None, (
        f'seeding left no playlist named {UNFILTERED_PLAYLIST!r}: {[p.get("name") for p in listed.json()]!r}'
    )

    tracks = requests.get(
        f'{manager}/api/users/{context["listener_id"]}/dynamic-playlists/{playlist["id"]}/tracks',
        headers={'x-api-key': api_key},
        timeout=TIMEOUT,
    )
    assert tracks.status_code == 200, tracks.text
    context['playlist_tracks'] = tracks.json()


@then('the scanned track is in it')
def _track_is_offered(context):
    rows = context['playlist_tracks']
    row = next((r for r in rows if r.get('title') == TRACK_TITLE), None)
    assert row is not None, (
        f'the playlist that filters on nothing does not offer {TRACK_FILE}: it returned '
        f'{[r.get("title") for r in rows]!r} -- the "no filter" rating range is being applied as one'
    )
    context['offered'] = row


@then('it is offered without a rating')
def _offered_unrated(context):
    # The other half of the claim: the row came through because it is unrated,
    # not because a stray rating for this listener let it pass the filter.
    assert context['offered'].get('rating') is None, context['offered']
