"""The system API key must actually reach the containers, and the pipeline
must refuse to deploy a release without one.

Both assertions exist because production ran for a day without a system key at
all: the deployment .env spells the key ``MUMA_API_KEY``, but
docker/docker-compose.yml only ever passed ``API_KEY`` through, and that entry
was empty. As long as services/music_manager/api_key.py still carried a
hardcoded literal fallback this was invisible; once the literal was removed the
resolution failed closed and every caller presenting the system key was
rejected -- LMS's scrobble and rating webhooks (401), the management UI's
/api/config (401) and /api/auth/verify (403).
"""

import subprocess
import textwrap
from pathlib import Path
from typing import Any

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE_FILE = REPO_ROOT / "docker" / "docker-compose.yml"
SECRETS_SCRIPT = REPO_ROOT / "scripts" / "ci" / "check-required-secrets.sh"

# Every service that authenticates to the music-manager API with the shared
# system key, or serves callers that do.
SYSTEM_KEY_SERVICES = ["music-manager"]


def load_compose() -> dict[str, Any]:
    return yaml.safe_load(COMPOSE_FILE.read_text(encoding="utf-8"))


def test_compose_passes_both_spellings_of_the_system_key():
    """api_key.resolve_system_api_key() reads API_KEY *or* MUMA_API_KEY, so a
    deployment that only defines one of them still needs both passed through:
    compose cannot express a nested "${API_KEY:-${MUMA_API_KEY}}" default."""
    compose = load_compose()
    for name in SYSTEM_KEY_SERVICES:
        environment = compose["services"][name]["environment"]
        for variable in ("API_KEY", "MUMA_API_KEY"):
            assert variable in environment, (
                f"{name} does not receive {variable}; a deployment .env that "
                f"only sets the other spelling leaves it with no system key"
            )


def run_secrets_check(env_content: str, lms_env_content: str) -> subprocess.CompletedProcess:
    return subprocess.run(
        ["bash", str(SECRETS_SCRIPT)],
        env={
            "PATH": "/usr/bin:/bin",
            "PROD_ENV_FILE": env_content,
            "PROD_ENV_FILE_LMS": lms_env_content,
        },
        capture_output=True,
        text=True,
        check=False,
    )


LMS_ENV = "VITE_GOOGLE_CLIENT_ID=some-client-id\n"
BASE_ENV = "GOOGLE_CLIENT_ID=some-client-id\n"


def test_secrets_check_rejects_a_release_without_any_system_key():
    result = run_secrets_check(BASE_ENV + "API_KEY=\n", LMS_ENV)
    assert result.returncode != 0
    assert "system API key" in result.stdout


def test_secrets_check_accepts_the_muma_api_key_spelling():
    """The production .env leaves API_KEY empty and sets MUMA_API_KEY; that is
    a valid deployment, not a missing secret."""
    result = run_secrets_check(
        BASE_ENV + textwrap.dedent("""\
            API_KEY=
            MUMA_API_KEY=a-real-key
        """),
        LMS_ENV,
    )
    assert result.returncode == 0, result.stdout


def test_secrets_check_accepts_the_api_key_spelling():
    result = run_secrets_check(BASE_ENV + "API_KEY=a-real-key\n", LMS_ENV)
    assert result.returncode == 0, result.stdout
