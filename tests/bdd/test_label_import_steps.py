"""Steps for features/label_import.feature.

The feature file is the description; this is only what the steps do.

Started by scripts/test/core-e2e.sh, which places the release fixture under the EPs
tree and seeds the two decided genres (e2e_stack_place_release, e2e_stack_seed_curation
in scripts/lib/e2e-stack.sh). Without that stack these skip.

Runs late, by conftest.FEATURE_ORDER: it triggers a scan, which genre_curation asserts
has not happened, and it retags a file, which the streaming steps of scan_to_listen
would notice if it happened underneath them. It stays ahead of genre_rejected, which
rewrites the other fixture's bytes and therefore has to be last.
"""

from __future__ import annotations

import os

import pytest
import requests
from pytest_bdd import given, parsers, scenarios, then, when

from .conftest import wait_for

pytestmark = pytest.mark.e2e

scenarios('features/label_import.feature')

TIMEOUT = 30
RELEASE_TITLE = 'Gabber Cowboy'


def _ep_path() -> str:
    """Where the release fixture sits, as music-manager sees it.

    Skipping rather than failing when it is unset matches conftest._base: a bare
    `pytest tests/bdd` with no stack up should say so, not report a broken chain.
    """
    path = os.getenv('MUMA_TEST_EP_PATH')
    if not path:
        pytest.skip('MUMA_TEST_EP_PATH is not set; start the stack with scripts/test/core-e2e.sh')
    return path


def _genre_row(manager: str, api_key: str, name: str) -> dict:
    response = requests.get(f'{manager}/api/rules/genres', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    body = response.json()
    rows = body if isinstance(body, list) else body.get('genres', [])
    row = next((r for r in rows if r.get('name') == name), None)
    assert row is not None, f'{name!r} is not in rules_genres: {[r.get("name") for r in rows]}'
    return row


def _release_track(manager: str, api_key: str) -> dict | None:
    """The library row for the release fixture, matched on its path.

    On its path and not on its title, because there may be two rows carrying it. The
    track key is built from title, duration and primary artist, so retagging a file
    whose artist tag went from one name to two produces a *new* track row and leaves
    the pre-tagging one behind with the media file no longer pointing at it. Matching
    on the path is what picks the row the file is actually attached to.
    """
    response = requests.get(
        f'{manager}/api/library/tracks',
        headers={'x-api-key': api_key},
        params={'q': RELEASE_TITLE, 'limit': 25},
        timeout=TIMEOUT,
    )
    if response.status_code != 200:
        return None
    body = response.json()
    rows = body if isinstance(body, list) else body.get('tracks', [])
    return next((row for row in rows if row.get('file_path') == _ep_path()), None)


@given(parsers.parse('a scene release by "{artist}" is sitting under the label folder "{label}"'))
def _release_is_in_place(artist, label, context):
    """Asserts nothing, and says why -- the same reasoning as the Top 100 fixture.

    The file is inside the LMS container rather than on this filesystem, so there is
    nothing here to stat. What proves it arrived is the tagging step below, which fails
    with a named error rather than an anonymous one.
    """
    path = _ep_path()
    assert label in path, f'the release fixture is not under a folder named {label!r}: {path}'
    context['release_artist'] = artist
    context['release_label'] = label


@given(parsers.parse('curation has already accepted the genres "{first}" and "{second}"'))
def _genres_are_accepted(manager, api_key, context, first, second):
    """Both must be white before either rule below will be taken.

    The rows themselves are seeded by the stack script, because a genre only ever enters
    rules_genres when the tagger meets it in a file and this release deliberately carries
    none. The decision is made here over the API rather than in that same SQL, and the
    difference matters: the endpoint refreshes the GenreRulesHelper the running tagger
    holds. Seeding a white row straight into the table would leave that process resolving
    both names as undecided, and the scenario would then pass or fail on a cache rather
    than on the rules it writes.
    """
    for name in (first, second):
        row = _genre_row(manager, api_key, name)
        decided = requests.post(
            f'{manager}/api/rules/genres/{row["id"]}/decide',
            headers={'x-api-key': api_key},
            json={'state': 'white'},
            timeout=TIMEOUT,
        )
        assert decided.status_code == 200, decided.text
        context.setdefault('genre_ids', {})[name] = row['id']


@when(parsers.parse('the curator records that the label "{label}" releases "{genre}"'))
def _label_releases_genre(manager, api_key, context, label, genre):
    response = requests.post(
        f'{manager}/api/curation/labels/{label}/genres',
        headers={'x-api-key': api_key},
        json={'genre_id': context['genre_ids'][genre]},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text


@when(parsers.parse('the curator records that "{subgenre}" rolls up into "{parent}"'))
def _subgenre_rolls_up(manager, api_key, subgenre, parent):
    response = requests.put(
        f'{manager}/api/curation/genres/{subgenre}/parents',
        headers={'x-api-key': api_key},
        json={'parents': [parent]},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text
    assert parent in response.json().get('parents', []), response.text


@when('the tagger is asked to tag the release')
def _tag_the_release(manager, api_key):
    """Synchronous, unlike the scan: this endpoint tags the one file and returns."""
    response = requests.post(
        f'{manager}/api/tagger/tag/file',
        headers={'x-api-key': api_key},
        params={'path': _ep_path()},
        timeout=120,
    )
    assert response.status_code == 200, response.text


@then('the release is in the library under the folder it was placed in')
def _release_is_indexed(manager, api_key, context):
    # The scan is a background task and may already have been running when this
    # feature asked for one, so this polls rather than reading once. Waiting for the
    # display artist rather than for the row: the row exists from the moment the file
    # was first seen, tags or no tags, and that would let every assertion below run
    # against a pre-tagging scan.
    def indexed():
        row = _release_track(manager, api_key)
        return row if row and row.get('display_artist') else None

    context['track'] = wait_for('the scanner to index the tagged release', indexed)


@then('the label above it on disk is the label on the track')
def _label_is_on_the_track(manager, api_key, context):
    assert context['track'].get('label') == context['release_label'], context['track']
    # And the same fact from the label's own side, which is what the label page reads.
    response = requests.get(
        f'{manager}/api/curation/labels/{context["release_label"]}',
        headers={'x-api-key': api_key},
        timeout=TIMEOUT,
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body.get('in_library'), body
    assert body.get('track_count', 0) >= 1, body


@then('both artists are in the library as names of their own')
def _artists_are_split(manager, api_key, context):
    # The first artist is also the track's primary one, which is the only per-track
    # artist any endpoint serves -- /api/library/tracks joins primary_artist_id alone.
    assert context['track'].get('artist') == 'Lil Texas', context['track']
    for name in ('Lil Texas', 'Albino'):
        response = requests.get(
            f'{manager}/api/curation/artists/{name}', headers={'x-api-key': api_key}, timeout=TIMEOUT
        )
        assert response.status_code == 200, response.text
        body = response.json()
        assert body.get('in_library'), f'{name!r} never became an artist of its own: {body!r}'
        # Exactly one, not "at least one": this database holds two tracks and only the
        # release carries either name, so an exact count is what ties the artist to
        # *this* file rather than to anything that happens to be in the library.
        assert body.get('track_count') == 1, f'{name!r} is not attached to the release alone: {body!r}'
    # The name the tag held before it was split must not survive as an artist of its own.
    unsplit = requests.get(
        f'{manager}/api/curation/artists/Lil Texas %26 Albino', headers={'x-api-key': api_key}, timeout=TIMEOUT
    )
    assert unsplit.status_code == 200, unsplit.text
    assert unsplit.json().get('track_count', 0) == 0, unsplit.json()


@then('the artist line as the file wrote it is kept as the display artist')
def _display_artist_survived(context):
    assert context['track'].get('display_artist') == context['release_artist'], context['track']


@then('the genre its label carries is on the track')
def _label_genre_is_on_the_track(context):
    genres = [g.strip() for g in (context['track'].get('genre') or '').split(',') if g.strip()]
    assert 'Uptempo Hardcore' in genres, (
        f'the release has no genre from its label: {genres!r} -- the file carries no genre tag, '
        'so the label rule is the only thing that could have put one here'
    )


@then('the broader genre it rolls up into is on the track as well')
def _parent_genre_is_on_the_track(context):
    genres = [g.strip() for g in (context['track'].get('genre') or '').split(',') if g.strip()]
    assert 'Hardcore' in genres, genres
