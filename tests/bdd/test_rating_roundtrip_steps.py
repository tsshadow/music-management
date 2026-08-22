"""Steps for features/rating_roundtrip.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up. Without it these
skip.
"""
from __future__ import annotations

import pytest
import requests
from pytest_bdd import given, scenarios, then, when

from .conftest import TRACK_FILE, TRACK_TITLE, wait_for

pytestmark = pytest.mark.e2e

scenarios('features/rating_roundtrip.feature')

TIMEOUT = 10


def _ratings(manager: str, api_key: str, username: str) -> list[dict]:
    response = requests.get(
        f'{manager}/api/rating/ratings/{username}',
        headers={'x-api-key': api_key},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text
    return response.json()


def _song(lms: str, subsonic_auth: dict) -> dict:
    response = requests.get(
        f'{lms}/rest/search3', params={'query': TRACK_TITLE, **subsonic_auth}, timeout=TIMEOUT
    )
    assert response.status_code == 200, response.text
    body = response.json()['subsonic-response']
    assert body['status'] == 'ok', f'LMS refused the search: {body.get("error")}'
    songs = body.get('searchResult3', {}).get('song', [])
    song = next((s for s in songs if s.get('title') == TRACK_TITLE), None)
    assert song is not None, f'LMS does not have the fixture track; it returned {songs!r}'
    return song


def _set_rating(lms: str, subsonic_auth: dict, song_id: str, stars: int) -> None:
    response = requests.get(
        f'{lms}/rest/setRating',
        params={'id': song_id, 'rating': stars, **subsonic_auth},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text
    body = response.json()['subsonic-response']
    assert body['status'] == 'ok', f'LMS refused the rating: {body.get("error")}'


def _wait_for_rating(manager, api_key, username, stars) -> dict:
    """The webhook is LMS calling music-manager, so it is not done when setRating
    answers. In practice it lands before the first poll; the wait is here so a
    failure says the rating never arrived rather than timing out anonymously."""
    def arrived():
        rows = _ratings(manager, api_key, username)
        return next((row for row in rows if row.get('rating') == stars), None)

    return wait_for(f'the rating of {stars} to reach music-manager', arrived, timeout=30)


@given('the track has no rating yet')
def _no_rating_yet(manager, api_key, subsonic_auth):
    rows = _ratings(manager, api_key, subsonic_auth['u'])
    assert rows == [], f'the stack came up with ratings already recorded: {rows!r}'


@when('the listener rates the track 4 stars')
def _rate_four(lms, subsonic_auth, context):
    context['song'] = _song(lms, subsonic_auth)
    _set_rating(lms, subsonic_auth, context['song']['id'], 4)


@then('LMS reports the track as rated 4')
def _lms_reports_four(lms, subsonic_auth):
    # Where the star actually lives. Asserting this separately keeps the next
    # step honest: if LMS never stored it, "music-manager has no rating" would
    # otherwise look like a broken webhook.
    assert _song(lms, subsonic_auth).get('userRating') == 4


@then('music-manager has the rating against the track it scanned')
def _manager_has_it_linked(manager, api_key, subsonic_auth):
    row = _wait_for_rating(manager, api_key, subsonic_auth['u'], 4)

    # The whole point. entity_id has to be music-manager's own track_uid, which
    # only happens when the webhook recognised LMS's path as the same file it
    # scanned; when it does not, the handler stores LMS's numeric track id and
    # the join below yields no path at all.
    assert row.get('file_path'), (
        f'the rating is not attached to any track in the library: {row!r} -- the webhook '
        f'fell back to LMS\'s own id, which stops resolving the moment LMS rescans'
    )
    assert str(row['file_path']).endswith(TRACK_FILE), (
        f'the rating landed on a different file: {row["file_path"]}'
    )


@when('the listener changes the rating to 1 star')
def _rate_one(lms, subsonic_auth, context):
    _set_rating(lms, subsonic_auth, context['song']['id'], 1)


@then('music-manager has the new rating against the same track')
def _manager_has_the_update(manager, api_key, subsonic_auth):
    row = _wait_for_rating(manager, api_key, subsonic_auth['u'], 1)
    assert str(row.get('file_path', '')).endswith(TRACK_FILE), row

    # One row, not two: the table is unique on (entity_type, entity_id, username)
    # and the handler upserts. Two rows would mean a listener's history of stars
    # accumulates instead of the current one being readable.
    rows = _ratings(manager, api_key, subsonic_auth['u'])
    assert len(rows) == 1, f'expected the rating to be updated in place, got {rows!r}'
