"""A release APK must not be built with the neutral server (issue #189, step 6).

``app/build.gradle`` falls back to ``https://music.example.org`` and no Google client id when
``MUMA_SERVER_URL`` / ``MUMA_GOOGLE_CLIENT_ID`` are unset. That is right for a debug build and a
shipped release with it is worse than a red job, so the build script stops first.
"""

import os
import subprocess
from pathlib import Path

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "muma-mobile-build-upload.sh"
GRADLE = Path(__file__).resolve().parents[2] / "services" / "muma-mobile" / "app" / "build.gradle"


def _run(build_type: str, **extra: str) -> subprocess.CompletedProcess:
    env = {
        "PATH": os.environ["PATH"],
        "APK_HOSTER_URL": "https://apk.example.org",
        "APK_HOSTER_PASSWORD": "not-a-secret",
    }
    env.update(extra)
    return subprocess.run(["bash", str(SCRIPT), build_type], env=env, capture_output=True, text=True, check=False)


def test_release_without_server_url_stops():
    result = _run("release", MUMA_GOOGLE_CLIENT_ID="id")
    assert result.returncode == 1
    assert "MUMA_SERVER_URL is not set" in result.stderr


def test_release_without_google_client_id_stops():
    result = _run("release", MUMA_SERVER_URL="https://music.example.org")
    assert result.returncode == 1
    assert "MUMA_GOOGLE_CLIENT_ID is not set" in result.stderr


def test_release_without_api_url_stops():
    result = _run(
        "release",
        MUMA_SERVER_URL="https://music.example.org",
        MUMA_GOOGLE_CLIENT_ID="id",
        MUMA_OWN_DOMAIN="example.org",
    )
    assert result.returncode == 1
    assert "MUMA_API_URL is not set" in result.stderr


def test_release_without_own_domain_stops():
    result = _run(
        "release",
        MUMA_SERVER_URL="https://music.example.org",
        MUMA_GOOGLE_CLIENT_ID="id",
        MUMA_API_URL="https://muma.example.org",
    )
    assert result.returncode == 1
    assert "MUMA_OWN_DOMAIN is not set" in result.stderr


def test_gradle_reads_the_properties_the_script_names():
    text = GRADLE.read_text()
    for name in (
        "muma.serverUrl",
        "muma.googleClientId",
        "muma.apiUrl",
        "MUMA_SERVER_URL",
        "MUMA_GOOGLE_CLIENT_ID",
        "muma.ownDomain",
        "MUMA_OWN_DOMAIN",
    ):
        assert name in text
