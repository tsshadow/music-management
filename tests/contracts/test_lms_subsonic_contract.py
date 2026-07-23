"""
First LMS / OpenSubsonic contract test (Task 5 of the test plan).

This test does NOT manage the Docker test stack itself: it assumes
`docker/compose.test.yml` is already running and reachable on the host ports
below (see scripts/test/contracts.sh, which starts the stack, imports the
fixture track, and tears everything down again).

It proves the minimal "golden path" contract that Ultrasonic and the frontend
rely on:
- the server is reachable;
- login/authentication works (delegated to music-manager, see
  MusicManagementPasswordService.cpp);
- the fixture track becomes visible via OpenSubsonic search;
- its metadata matches what was tagged into the fixture;
- streaming the track returns audio bytes.

Assertions are made against individual fields, not full literal response
snapshots (see plan 4.2), so an unrelated extra property never breaks this test.
"""
import json
import time
from pathlib import Path

import pytest
import requests

MUSIC_MANAGER_URL = "http://localhost:18000/api"
LMS_URL = "http://localhost:15082"
SUBSONIC_CLIENT = "muma-contract-test"
SUBSONIC_VERSION = "1.16.1"

TEST_USERNAME = "ci-contract-admin"
TEST_PASSWORD = "ci-contract-password"

FIXTURE_EXPECTED_PATH = (
    Path(__file__).resolve().parents[1] / "fixtures" / "expected" / "ci-test-track-001.json"
)


def wait_until(predicate, timeout=60, interval=1, description="condition"):
    """Poll `predicate` until it returns a truthy value or `timeout` seconds pass.

    Never uses a fixed sleep for the whole duration: fails fast once the
    condition is met, and reports a clear error on timeout.
    """
    deadline = time.monotonic() + timeout
    last_result = None
    while time.monotonic() < deadline:
        last_result = predicate()
        if last_result:
            return last_result
        time.sleep(interval)
    raise AssertionError(f"Timed out after {timeout}s waiting for: {description} (last result: {last_result!r})")


@pytest.fixture(scope="module")
def expected_track():
    with open(FIXTURE_EXPECTED_PATH, encoding="utf-8") as f:
        return json.load(f)


@pytest.fixture(scope="module")
def admin_credentials():
    """Creates the first admin user in music-manager via the setup endpoint.

    This also triggers notify_server_sync_users(), which pushes the new user
    to LMS immediately (see routers/users.py: setup_admin -> notify_server_sync_users).
    That sync is fire-and-forget on the LMS side (MumaResource "/users/sync"
    calls _userSynchronizer.syncUsers() asynchronously and returns immediately),
    so we poll until LMS actually recognizes the user (via ping.view) before
    handing back the credentials.
    """
    resp = requests.get(f"{MUSIC_MANAGER_URL}/auth/setup-status", timeout=10)
    resp.raise_for_status()
    if resp.json().get("setup_required"):
        resp = requests.post(
            f"{MUSIC_MANAGER_URL}/auth/setup",
            json={"username": TEST_USERNAME, "password": TEST_PASSWORD},
            timeout=10,
        )
        assert resp.status_code == 200, resp.text

    def user_synced_into_lms():
        ping_resp = _subsonic_get("ping.view", TEST_USERNAME, TEST_PASSWORD)
        return ping_resp.status_code == 200 and ping_resp.json()["subsonic-response"]["status"] == "ok"

    wait_until(user_synced_into_lms, timeout=30, interval=1, description="admin user synced into LMS")
    return TEST_USERNAME, TEST_PASSWORD


@pytest.fixture(scope="module")
def media_library(admin_credentials):
    """Registers /music as a media library on the test LMS and triggers a scan.

    See MumaResource.cpp: POST /muma/api/admin/libraries (query-param u/p auth,
    delegated to music-manager) creates the library, and
    IScannerService::requestReload() only reloads settings (it does NOT scan).
    An explicit Subsonic /rest/startScan.view call (admin-only) is required to
    actually trigger a scan of the newly registered library.
    """
    username, password = admin_credentials

    def create_library():
        create_resp = requests.post(
            f"{LMS_URL}/muma/api/admin/libraries",
            params={"u": username, "p": password},
            json={"name": "ci-test-library", "path": "/music"},
            timeout=10,
        )
        # 403 here means the isAdmin flag from music-manager's user sync hasn't
        # landed in LMS's local DB yet (getOrCreateUser() creates a REGULAR user
        # on first successful password check, independently of the sync); keep
        # polling instead of failing immediately.
        if create_resp.status_code == 403:
            return None
        return create_resp

    resp = wait_until(create_library, timeout=30, interval=1, description="admin flag synced into LMS for media library creation")
    assert resp.status_code == 200, resp.text
    library = resp.json()

    scan_resp = _subsonic_get("startScan.view", username, password)
    assert scan_resp.status_code == 200, scan_resp.text

    def scan_finished():
        status_resp = _subsonic_get("getScanStatus.view", username, password)
        if status_resp.status_code != 200:
            return False
        scan_status = status_resp.json()["subsonic-response"]["scanStatus"]
        return scan_status.get("scanning") is False and scan_status.get("lastScan") is not None

    wait_until(scan_finished, timeout=60, interval=1, description="LMS library scan to finish")
    return library


def _subsonic_get(endpoint, username, password, **params):
    query = {
        "u": username,
        "p": password,
        "v": SUBSONIC_VERSION,
        "c": SUBSONIC_CLIENT,
        "f": "json",
        **params,
    }
    resp = requests.get(f"{LMS_URL}/rest/{endpoint}", params=query, timeout=10)
    return resp


def test_server_is_reachable():
    resp = requests.get(
        f"{LMS_URL}/rest/ping.view",
        params={"u": "nobody", "p": "wrong", "v": SUBSONIC_VERSION, "c": SUBSONIC_CLIENT, "f": "json"},
        timeout=10,
    )
    assert resp.status_code == 200


def test_login_works(admin_credentials):
    username, password = admin_credentials
    resp = _subsonic_get("ping.view", username, password)
    assert resp.status_code == 200
    body = resp.json()
    assert body["subsonic-response"]["status"] == "ok"


def test_login_fails_with_invalid_credentials():
    resp = _subsonic_get("ping.view", TEST_USERNAME, "definitely-not-the-password")
    assert resp.status_code == 200
    body = resp.json()
    assert body["subsonic-response"]["status"] == "failed"


def test_fixture_track_is_findable_with_correct_metadata(admin_credentials, media_library, expected_track):
    username, password = admin_credentials

    def find_track():
        # Subsonic search3 matches standard tags (title/artist/album), not our
        # custom MUSIC_MANAGEMENT_ID frame, so we search by title here.
        resp = _subsonic_get(
            "search3.view",
            username,
            password,
            query=expected_track["title"],
        )
        if resp.status_code != 200:
            return None
        result = resp.json()["subsonic-response"].get("searchResult3", {})
        songs = result.get("song", [])
        for song in songs:
            if song.get("title") == expected_track["title"]:
                return song
        return None

    song = wait_until(find_track, timeout=60, interval=2, description="fixture track visible via OpenSubsonic search3")

    assert song["title"] == expected_track["title"]
    assert song["artist"] == expected_track["artist"]
    assert song["album"] == expected_track["album"]
    assert song["genre"] == expected_track["genre"]
    assert expected_track["duration_seconds_min"] <= song["duration"] <= expected_track["duration_seconds_max"]

    pytest.song_id = song["id"]  # stash for the streaming test below


def test_stream_returns_audio_bytes(admin_credentials):
    username, password = admin_credentials
    song_id = getattr(pytest, "song_id", None)
    assert song_id, "test_fixture_track_is_findable_with_correct_metadata must run first"

    resp = _subsonic_get("stream.view", username, password, id=song_id)
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type", "").startswith("audio/")
    assert len(resp.content) > 0
