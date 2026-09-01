"""Steps for features/genre_curation.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up and tags the
fixture. Without it these skip.
"""

from __future__ import annotations

import pytest
import requests
from pytest_bdd import given, scenarios, then

from .conftest import FIXTURE_GENRE, TRACK_TITLE, curation_queue, wait_for, wait_for_fixture_track

pytestmark = pytest.mark.e2e

scenarios('features/genre_curation.feature')

TIMEOUT = 30


def _library_genres(manager: str, api_key: str) -> list[dict]:
    """What the sidebar shows: genres that actually have tracks behind them."""
    response = requests.get(f'{manager}/api/library/genres', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    return response.json()


@given('no track carries that genre yet')
def _no_track_has_it(manager, api_key):
    # This feature runs before any other triggers a scan, which is what makes
    # the claim observable. Give another feature a scan in its Background that
    # runs earlier, and this stops holding.
    listed = [row.get('genre') for row in _library_genres(manager, api_key)]
    assert FIXTURE_GENRE not in listed, (
        f'{FIXTURE_GENRE} already has tracks behind it before this feature scanned: {listed!r}'
    )


@then('the track carries its genre')
def _track_carries_the_genre(manager, api_key):
    # Polling because the scan is a background task, and this is a field of a
    # row that may well already exist appearing later than the row did.
    def has_genre():
        track = wait_for_fixture_track(manager, api_key)
        return track if FIXTURE_GENRE in str(track.get('genre') or '') else None

    track = wait_for(f'the scan to attach {FIXTURE_GENRE} to the track', has_genre, timeout=60)
    assert TRACK_TITLE in str(track.get('title')), track


@then('the library lists that genre with the track against it')
def _genre_is_listed_with_a_count(manager, api_key):
    # The sidebar's own view. It counted nothing for as long as it existed,
    # because it joins the curated table against the per-track table and the
    # latter had no rows -- exactly the state this scenario walks out of.
    rows = _library_genres(manager, api_key)
    row = next((r for r in rows if r.get('genre') == FIXTURE_GENRE), None)
    assert row is not None, f'{FIXTURE_GENRE} has tracks but is not listed: {rows!r}'
    assert row.get('count', 0) >= 1, f'{FIXTURE_GENRE} is listed but no track counts towards it: {row!r}'


@then('the genre is still waiting for a decision')
def _genre_still_queued(manager, api_key):
    queued = [row.get('name') for row in curation_queue(manager, api_key)]
    assert FIXTURE_GENRE in queued, f'{FIXTURE_GENRE} left the curation queue without anyone deciding on it: {queued!r}'
