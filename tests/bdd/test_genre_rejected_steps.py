"""Steps for features/genre_rejected.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up and tags the
fixture. Without it these skip.

Runs last, by conftest.FEATURE_ORDER: the retag rewrites the fixture's bytes,
and scan_to_listen.feature compares a streamed copy against the size LMS
indexed. genre_decision.feature has already approved the genre by the time this
runs; a rejection is a decision like any other and does not care what the
previous one was.
"""

from __future__ import annotations

import pytest
import requests
from pytest_bdd import given, scenarios, then, when

from .conftest import FIXTURE_GENRE, TRACK_TITLE, wait_for, wait_for_fixture_track

pytestmark = pytest.mark.e2e

scenarios('features/genre_rejected.feature')

TIMEOUT = 30
DECISION_REASON = 'genre_decision'


def _headers(api_key: str) -> dict:
    return {'x-api-key': api_key}


def _genre_id(manager: str, api_key: str) -> int:
    response = requests.get(f'{manager}/api/rules/genres', headers=_headers(api_key), timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    rows = response.json()
    rows = rows if isinstance(rows, list) else rows.get('genres', [])
    row = next((r for r in rows if r.get('name') == FIXTURE_GENRE), None)
    assert row is not None, f'{FIXTURE_GENRE} is not in the rules table at all: {[r.get("name") for r in rows]!r}'
    return row['id']


def _pending(manager: str, api_key: str) -> dict:
    response = requests.get(f'{manager}/api/tagger/retag/pending', headers=_headers(api_key), timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    return response.json()


def _lms_song(lms: str, subsonic_auth: dict) -> dict:
    response = requests.get(f'{lms}/rest/search3', params={'query': TRACK_TITLE, **subsonic_auth}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    body = response.json()['subsonic-response']
    assert body['status'] == 'ok', f'LMS refused the search: {body.get("error")}'
    songs = body.get('searchResult3', {}).get('song', [])
    song = next((s for s in songs if s.get('title') == TRACK_TITLE), None)
    assert song is not None, f'LMS does not have the fixture track; it returned {songs!r}'
    return song


@given('the track carries its genre')
def _track_has_the_genre(manager, api_key, context):
    # The state genre_curation.feature walked into, asserted rather than assumed
    # because a rejection of a genre the track does not carry would prove nothing.
    track = wait_for_fixture_track(manager, api_key)
    assert FIXTURE_GENRE in str(track.get('genre') or ''), (
        f'the fixture does not carry {FIXTURE_GENRE} to begin with: {track.get("genre")!r}'
    )
    context['track'] = track


@when('the curator rejects the genre')
def _reject(manager, api_key, context):
    genre_id = _genre_id(manager, api_key)
    response = requests.post(
        f'{manager}/api/rules/genres/{genre_id}/decide',
        headers=_headers(api_key),
        json={'state': 'black'},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text
    context['genre_id'] = genre_id


@then("the track's file is waiting for a retag")
def _file_is_marked(manager, api_key):
    def marked():
        summary = _pending(manager, api_key)
        return next((r for r in summary.get('by_reason', []) if r.get('reason') == DECISION_REASON), None)

    reason = wait_for(f'the decision to mark the file for retag as {DECISION_REASON!r}', marked, timeout=30)
    assert reason.get('count', 0) >= 1, reason


@when('the retag is run')
def _run_retag(manager, api_key):
    # A background task: 200 means started, 409 that a run is already going --
    # which the marked file would be picked up by all the same.
    response = requests.post(f'{manager}/api/tagger/retag/run', headers=_headers(api_key), timeout=TIMEOUT)
    assert response.status_code in (200, 409), response.text


@then('the retag queue drains')
def _queue_drains(manager, api_key):
    # The tagger marks a file processed once it has rewritten it, so an empty
    # queue is the tagger saying it is done with this file -- not that it wrote
    # anything in particular, which the next steps are for.
    def drained():
        summary = _pending(manager, api_key)
        return summary if summary.get('total', 1) == 0 else None

    wait_for('the tagger to work through the retag queue', drained, timeout=120)


@then('the track no longer carries the genre')
def _genre_gone_from_library(manager, api_key):
    # The scanner runs after the tagger in the same retag, so this reads what the
    # scanner made of the rewritten file. Polled: the scan is the second half of
    # a background task whose first half is what the previous step waited for.
    def gone():
        track = wait_for_fixture_track(manager, api_key)
        return track if FIXTURE_GENRE not in str(track.get('genre') or '') else None

    track = wait_for(f'the scanner to drop {FIXTURE_GENRE} from the track', gone, timeout=120)
    assert TRACK_TITLE in str(track.get('title')), track


@when('LMS rescans its library')
def _lms_rescan(lms, subsonic_auth):
    response = requests.get(f'{lms}/rest/startScan.view', params=subsonic_auth, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    assert response.json()['subsonic-response']['status'] == 'ok', response.text

    def finished():
        status = requests.get(f'{lms}/rest/getScanStatus.view', params=subsonic_auth, timeout=TIMEOUT)
        body = status.json()['subsonic-response']
        return body if body.get('scanStatus', {}).get('scanning') is False else None

    wait_for('LMS to finish rescanning', finished, timeout=60)


@then('LMS no longer reports the genre on the track')
def _genre_gone_from_lms(lms, subsonic_auth):
    # LMS reads the tag straight from the file, so this is the only step that
    # proves the bytes changed: music-manager's own view could be right about a
    # file it never rewrote. Polled once more because LMS reports "not
    # scanning" a moment before its index is queryable.
    def gone():
        song = _lms_song(lms, subsonic_auth)
        genres = [song.get('genre')] + [g.get('name') for g in song.get('genres', [])]
        return song if FIXTURE_GENRE not in [g for g in genres if g] else None

    song = wait_for(f'LMS to stop reporting {FIXTURE_GENRE} on the track', gone, timeout=30)
    assert song.get('title') == TRACK_TITLE, song
