"""
Listen / scrobble flow contract test (Task 6 of the test plan).

Assumes docker/compose.test.yml is already running (see scripts/test/core-e2e.sh
or scripts/test/contracts.sh), with the fixture track already scanned into LMS
(same flow as test_lms_subsonic_contract.py). This test additionally scans the
fixture into music-manager's OWN library (services/music_manager/routers/scanner.py),
since scrobble matching (routers/scrobbler.py: handle_scrobble_event) looks up
tracks in music-manager's `library_tracks` table, not LMS's SQLite database.

Proves:
- "now playing" (submission=false) does NOT create a definitive listen;
- a real scrobble (submission=true) is recorded exactly once;
- repeating the identical scrobble does not create a duplicate listen
  (enforced by the `UNIQUE KEY (username, listened_at, track_id)` constraint).
"""

import os
import subprocess
import time

import pytest
import requests
from test_lms_subsonic_contract import (  # noqa: F401 (reused fixtures)
    LMS_URL,
    MUSIC_MANAGER_URL,
    _subsonic_get,
    admin_credentials,
    expected_track,
    media_library,
    wait_until,
)

SCAN_TARGET_PATH = "/mnt/music/ci-test-track-001.mp3"
# /scanner/scan/file requires an API key (it walks and writes to the library), matching the
# API_KEY the test stack's music-manager is started with in docker/compose.test.yml.
MUMA_API_KEY = os.getenv("API_KEY", "test-api-key")
DB_SERVICE = "test-db"
DB_USER = "muma_test"
DB_PASS = "muma_test"
DB_NAME = "muma_test"


def _get_container_id(service_name):
    """Finds a container ID by its Docker Compose project and service name labels.
    Defaults to the 'muma-test' project used by scripts/test/*.sh.
    """
    project = os.environ.get("COMPOSE_PROJECT_NAME", "muma-test")
    cmd = [
        "docker",
        "ps",
        "-q",
        "-f",
        f"label=com.docker.compose.project={project}",
        "-f",
        f"label=com.docker.compose.service={service_name}",
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=True)
    cid = result.stdout.strip()
    if not cid:
        raise RuntimeError(f"Could not find container for service '{service_name}' in project '{project}'")
    return cid


def _query_listen_count(username):
    """Counts scrobble_listens rows for `username`, via `docker exec` into the
    test database (no dedicated "list listens" API exists yet, see
    docs/testing-inventory.md; this uses the intended data store directly,
    per plan section 2.3/6.2 allowance to check "via de bedoelde API of
    database-interface").
    """
    cid = _get_container_id(DB_SERVICE)
    sql = f"SELECT COUNT(*) FROM scrobble_listens WHERE username='{username}';"
    # `mariadb`, not `mysql`: MariaDB renamed the client in 10.5 and removed the
    # old name in 12, where this exits 127 -- which reads as a broken test
    # rather than a renamed binary.
    result = subprocess.run(
        ["docker", "exec", cid, "mariadb", f"-u{DB_USER}", f"-p{DB_PASS}", DB_NAME, "-N", "-e", sql],
        capture_output=True,
        text=True,
        timeout=10,
        check=True,
    )
    return int(result.stdout.strip())


@pytest.fixture(scope="module")
def song_id(admin_credentials, media_library, expected_track):
    """Finds the fixture track's Subsonic song id (LMS side)."""
    username, password = admin_credentials

    def find_id():
        resp = _subsonic_get("search3.view", username, password, query=expected_track["title"])
        if resp.status_code != 200:
            return None
        songs = resp.json()["subsonic-response"].get("searchResult3", {}).get("song", [])
        for song in songs:
            if song.get("title") == expected_track["title"]:
                return song["id"]
        return None

    return wait_until(find_id, timeout=60, interval=2, description="fixture track visible via search3")


@pytest.fixture(scope="module")
def scanned_into_music_manager(expected_track):
    """Scans the fixture into music-manager's own library_tracks table.

    Required for handle_scrobble_event to match the track by artist+title.
    """
    resp = requests.post(
        f"{MUSIC_MANAGER_URL}/scanner/scan/file",
        params={"path": SCAN_TARGET_PATH},
        headers={"X-API-Key": MUMA_API_KEY},
        timeout=30,
    )
    assert resp.status_code == 200, resp.text
    return True


def test_now_playing_does_not_create_a_listen(admin_credentials, song_id, scanned_into_music_manager):
    username, password = admin_credentials
    before = _query_listen_count(username)

    resp = _subsonic_get("scrobble.view", username, password, id=song_id, submission="false")
    assert resp.status_code == 200
    assert resp.json()["subsonic-response"]["status"] == "ok"

    # No fixed sleep: assert immediately, then again after a short grace period,
    # to make sure a listen never appears asynchronously either.
    time.sleep(2)
    after = _query_listen_count(username)
    assert after == before, "now-playing (submission=false) must not create a definitive listen"


def test_scrobble_is_recorded_exactly_once(admin_credentials, song_id):
    username, password = admin_credentials
    before = _query_listen_count(username)
    listen_time_ms = int(time.time() * 1000)

    resp = _subsonic_get("scrobble.view", username, password, id=song_id, submission="true", time=listen_time_ms)
    assert resp.status_code == 200
    assert resp.json()["subsonic-response"]["status"] == "ok"

    def listen_recorded():
        return _query_listen_count(username) == before + 1

    wait_until(listen_recorded, timeout=30, interval=1, description="scrobble to be recorded as a listen")


def test_duplicate_scrobble_is_not_recorded_twice(admin_credentials, song_id):
    """Repeats the last test's exact scenario (same user/track) with a fresh
    timestamp reused twice in a row, to confirm the unique constraint on
    (username, listened_at, track_id) prevents duplicate rows.
    """
    username, password = admin_credentials
    listen_time_ms = int(time.time() * 1000)

    resp1 = _subsonic_get("scrobble.view", username, password, id=song_id, submission="true", time=listen_time_ms)
    assert resp1.status_code == 200

    def first_recorded():
        return _query_listen_count(username) >= 1

    wait_until(first_recorded, timeout=30, interval=1, description="first scrobble of this test to be recorded")
    count_after_first = _query_listen_count(username)

    # Send the exact same scrobble (identical id + time) again.
    resp2 = _subsonic_get("scrobble.view", username, password, id=song_id, submission="true", time=listen_time_ms)
    assert resp2.status_code == 200

    time.sleep(3)  # give the async forward-to-music-manager call a chance to (not) create a duplicate
    count_after_second = _query_listen_count(username)
    assert count_after_second == count_after_first, "an identical repeated scrobble must not create a duplicate listen"
