"""
LMS outbox contract tests: listens (issue #67, bug report 075, docs/designs/lms-listen-outbox/) and
rating changes (issue #222, docs/designs/lms-rating-outbox/).

A listen played while music-manager is down used to be lost: LMS's relay gave up after two
back-to-back retries. Since LMS database version 125 LMS writes the listen to its outbox first and
delivers it once music-manager is back. This stops the test stack's music-manager container,
scrobbles through LMS, starts music-manager again and waits for the listen to arrive. Since version
128 a rating change takes the same way: the rating cases rate or clear the fixture track during an
outage and wait for `rating_tracks` to hold the last state.

Runs last in this directory on purpose (file order): it stops and starts music-manager, and the
other contract modules should not share a stack with a container that has just restarted.

The scrobble and the ratings are signed with a Subsonic token (`u`/`t`/`s`), not a password. LMS checks a password
against music-manager, which is down at that moment. It checks a token against its own
`auth_token` table.
"""

import contextlib
import hashlib
import subprocess
import time

import requests
from test_listen_scrobble_flow import (  # noqa: F401 (reused fixtures)
    DB_NAME,
    DB_PASS,
    DB_SERVICE,
    DB_USER,
    _get_container_id,
    _query_listen_count,
    scanned_into_music_manager,
    song_id,
)
from test_lms_subsonic_contract import (  # noqa: F401 (reused fixtures)
    LMS_URL,
    MUSIC_MANAGER_URL,
    SUBSONIC_CLIENT,
    SUBSONIC_VERSION,
    admin_credentials,
    expected_track,
    media_library,
    wait_until,
)

MUSIC_MANAGER_SERVICE = "music-manager"
OUTAGE_TOKEN = "ci-contract-outbox-token-0123456789"


def _issue_admin_token(username, password):
    """Sets the admin's Subsonic token through LMS's admin route while music-manager is still up."""

    def issue():
        resp = requests.put(
            f"{LMS_URL}/muma/api/admin/subsonic-token",
            params={"u": username, "p": password, "username": username},
            json={"token": OUTAGE_TOKEN},
            timeout=10,
        )
        return resp if resp.status_code != 403 else None

    resp = wait_until(issue, timeout=30, interval=1, description="admin flag synced into LMS for token issue")
    assert resp.status_code == 200, resp.text


def _token_auth(username):
    """Subsonic token parameters for the admin: LMS checks them without asking music-manager."""
    salt = "0b0x5a17"
    return {
        "u": username,
        "t": hashlib.md5(f"{OUTAGE_TOKEN}{salt}".encode()).hexdigest(),
        "s": salt,
        "v": SUBSONIC_VERSION,
        "c": SUBSONIC_CLIENT,
        "f": "json",
    }


def _signed_scrobble(username, song, listen_time_ms):
    """A definitive scrobble signed with the admin's token: works while music-manager is down."""
    params = {**_token_auth(username), "id": song, "submission": "true", "time": listen_time_ms}
    return requests.get(f"{LMS_URL}/rest/scrobble.view", params=params, timeout=10)


def _signed_rating(username, song, stars):
    """Rates the song in LMS (0 clears the rating), signed with the admin's token."""
    params = {**_token_auth(username), "id": song, "rating": stars}
    resp = requests.get(f"{LMS_URL}/rest/setRating", params=params, timeout=10)
    assert resp.status_code == 200, resp.text
    assert resp.json()["subsonic-response"]["status"] == "ok", resp.text


def _query_track_ratings(username):
    """`rating_tracks` rows of `username` for tracks, as {entity_id: rating}, via the test database."""
    cid = _get_container_id(DB_SERVICE)
    sql = f"SELECT entity_id, rating FROM rating_tracks WHERE username='{username}' AND entity_type='track';"
    result = subprocess.run(
        ["docker", "exec", cid, "mariadb", f"-u{DB_USER}", f"-p{DB_PASS}", DB_NAME, "-N", "-e", sql],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    rows = (line.split("\t") for line in result.stdout.splitlines() if line.strip())
    return {entity_id: int(rating) for entity_id, rating in rows}


def _music_manager_healthy():
    try:
        return requests.get(MUSIC_MANAGER_URL.removesuffix("/api") + "/health", timeout=3).status_code == 200
    except requests.RequestException:
        return False


@contextlib.contextmanager
def _music_manager_stopped():
    """Stops music-manager for the body, starts it again after and waits until it is healthy."""
    music_manager = _get_container_id(MUSIC_MANAGER_SERVICE)
    subprocess.run(["docker", "stop", "-t", "5", music_manager], check=True, capture_output=True, timeout=60)
    try:
        yield
    finally:
        subprocess.run(["docker", "start", music_manager], check=True, capture_output=True, timeout=60)
    wait_until(_music_manager_healthy, timeout=120, interval=2, description="music-manager healthy again")


def _fixture_track_rated(username, song, stars):
    """Rates the song while music-manager is up and returns the entity_id music-manager stored it under."""
    before = _query_track_ratings(username)
    _signed_rating(username, song, stars)

    def stored():
        changed = {
            entity_id: rating
            for entity_id, rating in _query_track_ratings(username).items()
            if rating == stars and before.get(entity_id) != stars
        }
        return next(iter(changed), None)

    return wait_until(stored, timeout=60, interval=1, description=f"the rating of {stars} to reach music-manager")


def test_a_listen_made_while_music_manager_is_down_arrives_after_it_is_back(
    admin_credentials, song_id, scanned_into_music_manager
):
    username, password = admin_credentials
    _issue_admin_token(username, password)
    before = _query_listen_count(username)

    music_manager = _get_container_id(MUSIC_MANAGER_SERVICE)
    subprocess.run(["docker", "stop", "-t", "5", music_manager], check=True, capture_output=True, timeout=60)
    try:
        resp = _signed_scrobble(username, song_id, int(time.time() * 1000))
        assert resp.status_code == 200, resp.text
        assert resp.json()["subsonic-response"]["status"] == "ok", resp.text
        # Long enough for the relay to fail at least once and fall back on the outbox.
        time.sleep(8)
        assert _query_listen_count(username) == before, "music-manager is down; nothing can have arrived yet"
    finally:
        subprocess.run(["docker", "start", music_manager], check=True, capture_output=True, timeout=60)

    wait_until(_music_manager_healthy, timeout=120, interval=2, description="music-manager healthy again")
    # The relay's backoff tops out at 60 s, so the listen follows within about a minute.
    wait_until(
        lambda: _query_listen_count(username) == before + 1,
        timeout=120,
        interval=2,
        description="the listen made during the outage to arrive from LMS's outbox",
    )


def test_the_last_rating_made_while_music_manager_is_down_arrives_after_it_is_back(
    admin_credentials, song_id, scanned_into_music_manager
):
    username, password = admin_credentials
    _issue_admin_token(username, password)
    entity_id = _fixture_track_rated(username, song_id, 1)

    with _music_manager_stopped():
        _signed_rating(username, song_id, 2)
        _signed_rating(username, song_id, 4)
        # Long enough for the relay to fail at least once and keep the rating in the outbox.
        time.sleep(8)
        assert _query_track_ratings(username).get(entity_id) == 1, "music-manager is down; nothing can have changed"

    # The relay's backoff tops out at 60 s, so the rating follows within about a minute.
    wait_until(
        lambda: _query_track_ratings(username).get(entity_id) == 4,
        timeout=120,
        interval=2,
        description="the last rating made during the outage to arrive from LMS's outbox",
    )


def test_a_rating_cleared_while_music_manager_is_down_is_gone_after_it_is_back(
    admin_credentials, song_id, scanned_into_music_manager
):
    username, password = admin_credentials
    _issue_admin_token(username, password)
    entity_id = _fixture_track_rated(username, song_id, 3)

    with _music_manager_stopped():
        _signed_rating(username, song_id, 0)
        time.sleep(8)
        assert entity_id in _query_track_ratings(username), "music-manager is down; nothing can have changed"

    wait_until(
        lambda: entity_id not in _query_track_ratings(username),
        timeout=120,
        interval=2,
        description="the rating cleared during the outage to be removed from rating_tracks",
    )
