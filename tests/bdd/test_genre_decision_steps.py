"""Steps for features/genre_decision.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which brings the stack up and tags the
fixture. Without it these skip.

Runs after genre_curation, by conftest.FEATURE_ORDER: that feature asserts
the genre has no tracks behind it yet, and the scan this one needs in its
Background would make that false.
"""

from __future__ import annotations

import pytest
import requests
from pytest_bdd import scenarios, then, when

from .conftest import FIXTURE_GENRE, curation_queue, wait_for

pytestmark = pytest.mark.e2e

scenarios('features/genre_decision.feature')

TIMEOUT = 30
DECISION_REASON = 'genre_decision'


def _genre_rows(manager: str, api_key: str) -> list[dict]:
    """The whole rules table, every state; the queue is the subset in 'unknown'."""
    response = requests.get(f'{manager}/api/rules/genres', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    body = response.json()
    return body if isinstance(body, list) else body.get('genres', [])


def _fixture_genre_row(manager: str, api_key: str) -> dict:
    row = next((r for r in _genre_rows(manager, api_key) if r.get('name') == FIXTURE_GENRE), None)
    assert row is not None, f'{FIXTURE_GENRE} is not in the rules table at all'
    return row


@when('the curator approves the genre')
def _approve(manager, api_key, context):
    queued = next((row for row in curation_queue(manager, api_key) if row.get('name') == FIXTURE_GENRE), None)
    assert queued is not None, f'{FIXTURE_GENRE} left the queue before anyone decided on it'
    # No targets: a plain approval. Targets are how a genre is rewritten into
    # others, which is a different decision with a different effect on the file.
    response = requests.post(
        f'{manager}/api/rules/genres/{queued["id"]}/decide',
        headers={'x-api-key': api_key},
        json={'state': 'white'},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text
    context['genre_id'] = queued['id']


@then('the genre is no longer waiting for a decision')
def _left_the_queue(manager, api_key):
    queued = [row.get('name') for row in curation_queue(manager, api_key)]
    assert FIXTURE_GENRE not in queued, f'{FIXTURE_GENRE} is still in the curation queue after being approved'


@then('the decision is on record, so the tagger will not undo it')
def _decision_recorded(manager, api_key, context):
    row = _fixture_genre_row(manager, api_key)
    assert row.get('id') == context['genre_id'], row
    assert row.get('state') == 'white', f'the genre was approved but its state is {row.get("state")!r}'
    # decided_by is what the tagger checks before touching a row. The value is
    # whoever presented the key -- 'system' here, a username from the UI -- and
    # what matters is that it is not empty: an empty one reads as undecided.
    assert row.get('decided_by'), f'the decision was saved without recording who made it: {row!r}'
    assert row.get('decided_at'), f'the decision was saved without recording when: {row!r}'


@then('the library still lists the genre with the track against it')
def _still_listed(manager, api_key):
    response = requests.get(f'{manager}/api/library/genres', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    row = next((r for r in response.json() if r.get('genre') == FIXTURE_GENRE), None)
    assert row is not None, f'{FIXTURE_GENRE} vanished from the library listing on being approved'
    assert row.get('state') == 'white', row
    assert row.get('count', 0) >= 1, f'{FIXTURE_GENRE} is listed but lost its track: {row!r}'


@then("the track's file is queued for a retag because of the decision")
def _queued_for_retag(manager, api_key):
    # The mark is made after the decision is committed and its failure is only
    # logged, so a decision that saved without marking anything answers 200 all
    # the same. This is the only place that difference is visible.
    def marked():
        response = requests.get(f'{manager}/api/tagger/retag/pending', headers={'x-api-key': api_key}, timeout=TIMEOUT)
        assert response.status_code == 200, response.text
        summary = response.json()
        return next((r for r in summary.get('by_reason', []) if r.get('reason') == DECISION_REASON), None)

    reason = wait_for(f'the decision to mark a file for retag as {DECISION_REASON!r}', marked, timeout=30)
    assert reason.get('count', 0) >= 1, reason
