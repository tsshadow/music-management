"""
LMS listen outbox contract test (issue #67, bug report 075, docs/designs/lms-listen-outbox/).

A listen played while music-manager is down used to be lost: LMS's relay gave up after two
back-to-back retries. Since LMS database version 125 LMS writes the listen to its outbox first and
delivers it once music-manager is back. This stops the test stack's music-manager container,
scrobbles through LMS, starts music-manager again and waits for the listen to arrive.

Runs last in this directory on purpose (file order): it stops and starts music-manager, and the
other contract modules should not share a stack with a container that has just restarted.

The scrobble is signed with a Subsonic token (`u`/`t`/`s`), not a password. LMS checks a password
against music-manager, which is down at that moment. It checks a token against its own
`auth_token` table.
"""

import hashlib
import subprocess
import time

import requests
from test_listen_scrobble_flow import (  # noqa: F401 (reused fixtures)
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


def _signed_scrobble(username, song, listen_time_ms):
    """A definitive scrobble signed with the admin's token: works while music-manager is down."""
    salt = "0b0x5a17"
    params = {
        "u": username,
        "t": hashlib.md5(f"{OUTAGE_TOKEN}{salt}".encode()).hexdigest(),
        "s": salt,
        "v": SUBSONIC_VERSION,
        "c": SUBSONIC_CLIENT,
        "f": "json",
        "id": song,
        "submission": "true",
        "time": listen_time_ms,
    }
    return requests.get(f"{LMS_URL}/rest/scrobble.view", params=params, timeout=10)


def _music_manager_healthy():
    try:
        return requests.get(MUSIC_MANAGER_URL.removesuffix("/api") + "/health", timeout=3).status_code == 200
    except requests.RequestException:
        return False


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
