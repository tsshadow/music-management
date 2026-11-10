"""release:check-secrets checks what a release build needs, and no production variable.

Step 3b of docs/designs/ops-split/: the production host, its SSH key and its env
files belong to the operations repository, so this check must pass without them.
"""

import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "scripts" / "ci" / "check-required-secrets.sh"
COMPLETE = {
    "DOCKERHUB_USERNAME": "builder",
    "DOCKERHUB_TOKEN": "t",
    "APK_HOSTER_URL": "https://apk.example.org",
    "SIGNING_STORE_FILE": "/keystore",
    "MUMA_GOOGLE_CLIENT_ID": "client.apps.example.org",
}


def _run(**env: str) -> subprocess.CompletedProcess:
    """Run the check with exactly the given CI/CD variables."""
    return subprocess.run(
        ["bash", str(SCRIPT)], env={"PATH": "/usr/bin:/bin", **env}, capture_output=True, text=True, check=False
    )


def test_the_build_variables_alone_pass():
    result = _run(**COMPLETE)
    assert result.returncode == 0, result.stdout
    assert "PROD_" not in result.stdout


@pytest.mark.parametrize("missing", sorted(COMPLETE))
def test_each_build_variable_is_required(missing: str):
    env = {k: v for k, v in COMPLETE.items() if k != missing}
    result = _run(**env)
    assert result.returncode == 1
    assert "Missing required secret" in result.stdout


def test_the_player_client_id_may_have_its_own_variable():
    env = {k: v for k, v in COMPLETE.items() if k != "MUMA_GOOGLE_CLIENT_ID"}
    assert _run(**env, VITE_GOOGLE_CLIENT_ID="web.apps.example.org").returncode == 0


def test_a_docker_user_other_than_the_push_login_fails():
    assert _run(**COMPLETE, DOCKER_USER="builder").returncode == 0
    result = _run(**COMPLETE, DOCKER_USER="someone-else")
    assert result.returncode == 1
    assert "Mismatch" in result.stdout
