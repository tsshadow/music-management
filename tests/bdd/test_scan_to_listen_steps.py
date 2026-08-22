"""Steps for features/scan_to_listen.feature.

The feature file is the description of this chain; this is only what the steps
do. If the two disagree, the feature file is the one that is right and this is
the bug -- that is the whole reason the chain is written there rather than in a
docstring here. It replaced a plain pytest function that said the same thing,
which was deleted rather than kept alongside.

Started by scripts/test/core-e2e.sh, which brings the stack up and puts the
fixture in place. Without it these skip.
"""
from __future__ import annotations

import pytest
import requests
from pytest_bdd import given, scenarios, then, when

from .conftest import TRACK_FILE, TRACK_TITLE, stats, wait_for_fixture_track

pytestmark = pytest.mark.e2e

scenarios('features/scan_to_listen.feature')

# TRACK_FILE and TRACK_TITLE come from conftest and are two different strings on
# purpose: the library is keyed on the tag, not the path. The scanner stores TIT2
# as library_tracks.title, and /api/library/tracks searches title, artist and
# label -- so searching for the file name matches nothing however well the scan
# went.
#
# USERNAME is who the listen belongs to in music-manager's own records. Not the
# LMS account the Subsonic steps authenticate as; that one is created by the
# stack script and reaches the suite as the subsonic_auth fixture.
USERNAME = 'e2e'
TIMEOUT = 10


def _listen_count(manager: str, api_key: str) -> int:
    """How many matched listens music-manager is holding.

    A count, because a count is all there is -- see conftest.stats. So this
    cannot assert that the row is the right one, only that a row appeared where
    there was none, in a database that starts empty every run.
    """
    return stats(manager, api_key).get('total_scrobbles', 0)


# --- Given -------------------------------------------------------------------
# The background is the stack that scripts/test/core-e2e.sh brought up before
# pytest started. These assert rather than act: a Given that silently did nothing
# would let the whole scenario pass against no stack at all. "the test stack is
# running" is shared with the other features and lives in conftest.py.


@given('nothing has been listened to yet')
def _no_listens_yet(manager, api_key, context):
    # The stack is built from an empty database every run, so this is a
    # precondition rather than a cleanup. Recording it makes the assertion at the
    # end about *this* listen: without it, "there is one listen" would also hold
    # for a listen left behind by something else.
    context['listens_before'] = _listen_count(manager, api_key)
    assert context['listens_before'] == 0, (
        f'the stack came up with {context["listens_before"]} listens already recorded'
    )


# --- When / Then -------------------------------------------------------------


@then('the track is in the library under its own file name')
def _track_is_in_the_library(manager, api_key, context):
    track = wait_for_fixture_track(manager, api_key)
    assert str(track.get('file_path', '')).endswith(TRACK_FILE), (
        f'matched a track by title that is not the fixture: {track!r}'
    )
    context['track'] = track


@when('the mobile app searches for the track over the Subsonic API')
def _subsonic_search(lms, subsonic_auth, context):
    context['search'] = requests.get(
        f'{lms}/rest/search3',
        params={'query': TRACK_TITLE, **subsonic_auth},
        timeout=TIMEOUT,
    )


@then('the Subsonic search returns the track')
def _subsonic_search_returns_the_track(context):
    search = context['search']
    assert search.status_code == 200, search.text

    # Subsonic puts failures inside a 200, so the status has to be read out of
    # the body. This step asserted only on the HTTP code until the fixture step
    # learned to create a user and scan: it was passing on
    # {"status":"failed","error":{"code":40,"message":"Wrong username or
    # password."}} and proving nothing about LMS beyond that it was listening.
    body = search.json()['subsonic-response']
    assert body['status'] == 'ok', f'LMS refused the search: {body.get("error")}'

    songs = body.get('searchResult3', {}).get('song', [])
    titles = [song.get('title') for song in songs]
    assert TRACK_TITLE in titles, (
        f'LMS answered but does not have the fixture track; it returned {titles!r}'
    )
    # LMS's own id for the track, which is not music-manager's. The streaming
    # steps need it, and it only exists once LMS has scanned.
    context['song'] = next(song for song in songs if song.get('title') == TRACK_TITLE)


@when('the mobile app streams the track')
def _stream(lms, subsonic_auth, context):
    context['stream'] = requests.get(
        f'{lms}/rest/stream',
        params={'id': context['song']['id'], **subsonic_auth},
        timeout=TIMEOUT,
    )


@then('the audio comes back whole and unconverted')
def _audio_comes_back_whole(context):
    stream = context['stream']

    # Unlike the JSON endpoints, /rest/stream answers with real status codes: a
    # missing id is a 404 and a bad password a 400, not a 200 with an error in
    # it. So here the HTTP code is worth asserting on directly.
    assert stream.status_code == 200, f'{stream.status_code}: {stream.text[:200]}'
    assert stream.headers.get('Content-Type', '').startswith('audio/'), stream.headers

    # Byte-for-byte the file that was put on the volume. Comparing against the
    # size LMS itself advertised is what rules out a transcode: Subsonic servers
    # may re-encode on the way out, and a re-encoded stream is still audio, still
    # 200, and no longer the thing that was scanned.
    body = context['stream'].content
    assert len(body) == context['song']['size'], (
        f'streamed {len(body)} bytes, but LMS said the track is '
        f'{context["song"]["size"]}: it was converted on the way out'
    )
    assert body.startswith(b'ID3'), (
        f'streamed bytes do not start an MP3 file: {body[:16]!r}'
    )


@then('a player can ask for a single byte in the middle of it')
def _one_byte_can_be_fetched(lms, subsonic_auth, context):
    size = context['song']['size']
    offset = size // 2
    partial = requests.get(
        f'{lms}/rest/stream',
        params={'id': context['song']['id'], **subsonic_auth},
        headers={'Range': f'bytes={offset}-{offset}'},
        timeout=TIMEOUT,
    )

    # 206, not 200: a server that ignores Range answers 200 with the whole file,
    # which reads as success to anything that only checks the status code and
    # leaves a player unable to seek.
    assert partial.status_code == 206, (
        f'expected 206 for a range request, got {partial.status_code}'
    )
    assert partial.headers.get('Content-Range') == f'bytes {offset}-{offset}/{size}', (
        partial.headers.get('Content-Range')
    )
    assert len(partial.content) == 1, f'asked for one byte, got {len(partial.content)}'


@when('a listen is recorded for the track')
def _scrobble(manager, api_key, context):
    track = context['track']
    context['scrobble'] = requests.post(
        f'{manager}/api/scrobble/event',
        headers={'x-api-key': api_key},
        json={
            'artist_name': track.get('artist') or 'Unknown Artist',
            'track_title': track['title'],
            'username': USERNAME,
            'source': 'e2e',
        },
        timeout=TIMEOUT,
    )


@then('the listen is matched to the track that was scanned')
def _listen_is_matched(context):
    scrobble = context['scrobble']
    assert scrobble.status_code == 200, scrobble.text
    assert scrobble.json().get('matched') is True, (
        'the listen did not match a track: the scan and the scrobble disagree about its name'
    )


@then("the listen is in the library's own records")
def _listen_was_kept(manager, api_key, context):
    # The endpoint commits before it answers, so this reads straight away rather
    # than polling: a listen that needs waiting for is a bug, and a poll here
    # would hide it.
    after = _listen_count(manager, api_key)
    assert after == context['listens_before'] + 1, (
        f'the scrobble reported a match but the count went from '
        f'{context["listens_before"]} to {after}: it was answered, not stored'
    )
