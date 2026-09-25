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
import os
import time
from pathlib import Path

import pytest
import requests

MUSIC_MANAGER_PORT = os.environ.get("MUMA_TEST_PORT_MANAGER", "18000")
LMS_PORT = os.environ.get("MUMA_TEST_PORT_LMS", "15082")

MUSIC_MANAGER_URL = f"http://localhost:{MUSIC_MANAGER_PORT}/api"
LMS_URL = f"http://localhost:{LMS_PORT}"
SUBSONIC_CLIENT = "muma-contract-test"
SUBSONIC_VERSION = "1.16.1"

TEST_USERNAME = "ci-contract-admin"
TEST_PASSWORD = "ci-contract-password"

FIXTURE_EXPECTED_PATH = Path(__file__).resolve().parents[1] / "fixtures" / "expected" / "ci-test-track-001.json"


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

    resp = wait_until(
        create_library, timeout=30, interval=1, description="admin flag synced into LMS for media library creation"
    )
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


def test_song_carries_an_original_date_attribute(admin_credentials):
    """muma-mobile prefers the original release date, so it has to be on the wire.

    The `date` attribute carries this edition's date, which is not what the tagger resolves into
    ORIGINALDATE. Without a separate attribute the resolved value never reaches a client.
    """
    username, password = admin_credentials
    song_id = getattr(pytest, "song_id", None)
    assert song_id, "test_fixture_track_is_findable_with_correct_metadata must run first"

    resp = _subsonic_get("getSong.view", username, password, id=song_id)
    assert resp.status_code == 200, resp.text[:500]
    song = resp.json()["subsonic-response"]["song"]

    assert "originalDate" in song
    # The fixture library carries year-only dates, so the value may be a bare year or empty. What
    # this pins is that the attribute exists and never contradicts the year.
    if song["originalDate"] and song.get("year"):
        assert song["originalDate"].startswith(str(song["year"]))


def test_song_carries_the_version_fields_the_web_ui_reads(admin_credentials):
    """The browser collapses versions of one song on these, so they have to be on the wire.

    All four travel together on purpose. `isCanonical` says which version to show, and
    `versionScore` is what decides it while a work is being regrouped and its canonical is
    briefly unset -- without the score every candidate reads as zero and the first one wins by
    accident. That gap shipped once and cost nothing visible, which is exactly why it needs a
    test rather than a reader.

    `workId` is absent for a track muma has not grouped yet, which the browser reads as "its own
    song"; the fixture library has no muma behind it, so absence is the expected state here.
    """
    username, password = admin_credentials
    song_id = getattr(pytest, "song_id", None)
    assert song_id, "test_fixture_track_is_findable_with_correct_metadata must run first"

    resp = _subsonic_get("getSong.view", username, password, id=song_id)
    assert resp.status_code == 200, resp.text[:500]
    song = resp.json()["subsonic-response"]["song"]

    assert "isCanonical" in song, "the browser hides a track without this"
    assert "versionScore" in song, "the tie-break reads this and silently scores zero without it"
    # Nothing grouped this fixture, so it must read as a song of its own rather than as a
    # version of something else.
    assert song.get("workId") in (None, 0, "0"), song.get("workId")
    assert song["isCanonical"] in (True, "true", 1, "1"), song["isCanonical"]


def test_stream_returns_audio_bytes(admin_credentials):
    username, password = admin_credentials
    song_id = getattr(pytest, "song_id", None)
    assert song_id, "test_fixture_track_is_findable_with_correct_metadata must run first"

    resp = _subsonic_get("stream.view", username, password, id=song_id)
    assert resp.status_code == 200
    assert resp.headers.get("Content-Type", "").startswith("audio/")
    assert len(resp.content) > 0


def test_artist_cover_art_falls_back_to_release_artwork(admin_credentials, media_library, expected_track):
    """An artist MuMa has no picture for still serves an image.

    Only about a quarter of the artists in the real library have a fetched
    artist picture, so for the rest LMS emits a MuMa-backed cover art id whose
    proxied request 404s. The clients draw their generic placeholder for such a
    failure, which is what "every artist on the home screen has a picture"
    rules out: LMS falls back to the artist's own release artwork instead (see
    handleGetCoverArt in MediaRetrieval.cpp).
    """
    username, password = admin_credentials

    def find_artist():
        resp = _subsonic_get("search3.view", username, password, query=expected_track["artist"])
        if resp.status_code != 200:
            return None
        result = resp.json()["subsonic-response"].get("searchResult3", {})
        for artist in result.get("artist", []):
            if artist.get("name") == expected_track["artist"]:
                return artist
        return None

    artist = wait_until(
        find_artist, timeout=60, interval=2, description="fixture artist visible via OpenSubsonic search3"
    )

    cover_art_id = artist.get("coverArt")
    assert cover_art_id, "artists must always carry a cover art id, so clients have something to request"

    # The test stack's MuMa knows nothing about this artist, so the id points at
    # MuMa and the proxied fetch fails there; the response must still be an image.
    assert cover_art_id.startswith("muma-"), f"expected a MuMa-backed id, got {cover_art_id!r}"

    resp = _subsonic_get("getCoverArt.view", username, password, id=cover_art_id)
    assert resp.status_code == 200, resp.text[:500]
    assert resp.headers.get("Content-Type", "").startswith("image/")
    assert len(resp.content) > 0


def test_get_memories_answers_with_a_memories_node(admin_credentials, media_library):
    """The endpoint both clients read for the "today, X years ago" screens.

    The fixture library carries no day-precision release dates, so an EMPTY answer
    is the expected pass here: what is being proven is that the endpoint exists,
    authenticates, and returns a well-formed success response rather than an error.
    Asserting on a non-empty list would make this test depend on the calendar.
    """
    username, password = admin_credentials

    resp = _subsonic_get("getMemories.view", username, password, date="2026-08-02")

    assert resp.status_code == 200, resp.text[:500]
    body = resp.json()["subsonic-response"]
    assert body["status"] == "ok", body
    assert "memories" in body, body


def test_get_memories_accepts_a_single_year(admin_credentials, media_library):
    """One year's memories rather than every year's, which is what a year page asks for.

    Like the test above, an empty answer is the pass: the fixture library has no
    day-precision release dates, so what is proven here is that the parameter is
    accepted and still yields a well-formed success response.
    """
    username, password = admin_credentials

    resp = _subsonic_get("getMemories.view", username, password, date="2026-08-02", year=2025, maxPerYear=1000)

    assert resp.status_code == 200, resp.text[:500]
    body = resp.json()["subsonic-response"]
    assert body["status"] == "ok", body
    assert "memories" in body, body


def test_get_memories_rejects_an_unparseable_date(admin_credentials):
    """A malformed date is a client error, not an empty result."""
    username, password = admin_credentials

    resp = _subsonic_get("getMemories.view", username, password, date="2020-13-45")

    assert resp.status_code == 200, resp.text[:500]
    body = resp.json()["subsonic-response"]
    assert body["status"] == "failed", body
    assert body["error"]["code"] == 10, body


def test_get_memories_clamps_absurd_parameters(admin_credentials, media_library):
    """Out-of-range paging values are clamped into range rather than rejected."""
    username, password = admin_credentials

    resp = _subsonic_get("getMemories.view", username, password, date="2026-08-02", windowDays=999, maxPerYear=0)

    assert resp.status_code == 200, resp.text[:500]
    body = resp.json()["subsonic-response"]
    assert body["status"] == "ok", body


def _subsonic_post(endpoint, username, password, data):
    """A Subsonic call whose parameters travel in the body rather than the query string.

    getSongsByPath takes one `path` per track, and thirty of them run to several kilobytes --
    around where a request line starts meeting proxy buffer limits. The credentials stay in the
    query string, exactly as the mobile client's interceptor puts them there, so this also pins
    that the server merges both sources into one parameter map.
    """
    query = {
        "u": username,
        "p": password,
        "v": SUBSONIC_VERSION,
        "c": SUBSONIC_CLIENT,
        "f": "json",
    }
    return requests.post(f"{LMS_URL}/rest/{endpoint}", params=query, data=data, timeout=10)


def _fixture_song_path(username, password):
    song_id = getattr(pytest, "song_id", None)
    assert song_id, "test_fixture_track_is_findable_with_correct_metadata must run first"

    resp = _subsonic_get("getSong.view", username, password, id=song_id)
    assert resp.status_code == 200, resp.text[:500]
    song = resp.json()["subsonic-response"]["song"]
    assert song.get("path"), f"the song node carries no path: {song}"
    return song_id, song["path"]


def test_get_songs_by_path_resolves_a_path_to_a_playable_song(admin_credentials, media_library):
    """The bridge MuMa's personalized feeds stand on.

    MuMa ranks a feed and knows its tracks only by file path; this server knows them by id, and
    nothing else joins the two. If this call stops resolving, the release radar and the daily mix
    go silently empty in the car -- they would still list nothing rather than fail.
    """
    username, password = admin_credentials
    song_id, path = _fixture_song_path(username, password)

    resp = _subsonic_post("getSongsByPath.view", username, password, data=[("path", path)])

    assert resp.status_code == 200, resp.text[:500]
    body = resp.json()["subsonic-response"]
    assert body["status"] == "ok", body
    songs = body["songsByPath"]["song"]
    assert [song["id"] for song in songs] == [song_id]


def test_get_songs_by_path_answers_in_the_order_it_was_asked(admin_credentials, media_library):
    """The order is the feed. A quota per genre, a cap per artist and release date descending are

    all decided by MuMa, and a server that answered in its own order would replace the ranking
    with a different one without anybody noticing.
    """
    username, password = admin_credentials
    song_id, path = _fixture_song_path(username, password)

    resp = _subsonic_post(
        "getSongsByPath.view",
        username,
        password,
        data=[("path", "no/such/file.mp3"), ("path", path), ("path", "another/missing.flac")],
    )

    assert resp.status_code == 200, resp.text[:500]
    songs = resp.json()["subsonic-response"]["songsByPath"]["song"]
    # The two unknown paths drop out; the known one keeps its place rather than failing the call.
    assert [song["id"] for song in songs] == [song_id]


def test_get_songs_by_path_without_a_path_is_refused(admin_credentials, media_library):
    """A call with no paths is a caller bug, not an empty feed, and is answered as one."""
    username, password = admin_credentials

    resp = _subsonic_post("getSongsByPath.view", username, password, data={})

    assert resp.status_code == 200, resp.text[:500]
    body = resp.json()["subsonic-response"]
    assert body["status"] == "failed", body


# A queue is one parameter per track. The web player used to put a queue in the query string of
# savePlayQueue / createPlaylist and got 414 URI Too Long back for a long one; it now sends the
# track ids in a form-encoded POST body (OpenSubsonic `formPost`). These pin that LMS reads them
# there -- a few hundred entries is well past where a request line starts meeting proxy limits.
QUEUE_LENGTH = 400


def test_save_play_queue_accepts_the_queue_in_a_post_body(admin_credentials, media_library):
    username, password = admin_credentials
    song_id, _ = _fixture_song_path(username, password)

    data = [("id", song_id)] * QUEUE_LENGTH + [("current", song_id), ("playing", "false")]
    resp = _subsonic_post("savePlayQueue.view", username, password, data=data)

    assert resp.status_code == 200, resp.text[:500]
    assert resp.json()["subsonic-response"]["status"] == "ok", resp.text[:500]

    resp = _subsonic_get("getPlayQueue.view", username, password)
    assert resp.status_code == 200, resp.text[:500]
    queue = resp.json()["subsonic-response"]["playQueue"]
    entries = queue.get("entry", [])
    # The test library holds one track, and LMS keeps a track in a play queue once however often
    # it is listed -- so the proof that the body was read is that the queue is not empty and
    # points at that track, not a count of 400.
    assert [entry["id"] for entry in entries] == [song_id]

    # Leave the account's queue empty for whatever runs next: no id clears it.
    _subsonic_post("savePlayQueue.view", username, password, data={})


def test_create_playlist_accepts_the_song_ids_in_a_post_body(admin_credentials, media_library):
    username, password = admin_credentials
    song_id, _ = _fixture_song_path(username, password)
    name = "ci-contract-post-playlist"

    data = [("name", name)] + [("songId", song_id)] * QUEUE_LENGTH
    resp = _subsonic_post("createPlaylist.view", username, password, data=data)

    assert resp.status_code == 200, resp.text[:500]
    assert resp.json()["subsonic-response"]["status"] == "ok", resp.text[:500]

    resp = _subsonic_get("getPlaylists.view", username, password)
    playlists = resp.json()["subsonic-response"]["playlists"].get("playlist", [])
    created = [p for p in playlists if p["name"] == name]
    assert len(created) == 1, playlists
    try:
        assert created[0]["songCount"] == QUEUE_LENGTH
    finally:
        _subsonic_get("deletePlaylist.view", username, password, id=created[0]["id"])
