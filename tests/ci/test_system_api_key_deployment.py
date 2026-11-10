"""The system API key must actually reach the containers.

Both assertions exist because production ran for a day without a system key at
all: the deployment .env spells the key ``MUMA_API_KEY``, but
docker/docker-compose.yml only ever passed ``API_KEY`` through, and that entry
was empty. As long as services/music_manager/api_key.py still carried a
hardcoded literal fallback this was invisible; once the literal was removed the
resolution failed closed and every caller presenting the system key was
rejected -- LMS's scrobble and rating webhooks (401), the management UI's
/api/config (401) and /api/auth/verify (403).

The check that the production env file holds a key is the production deploy's,
in the operations repository (docs/designs/ops-split/).
"""

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


# Every container that tags a file and then announces it (services/tagger/announce.py):
# the bookkeeping needs the database, LMS needs its host and key, the scanner needs the
# music-manager URL and the system key.
ANNOUNCING_SERVICES = ["importer_worker", "youtube_worker", "soundcloud_worker", "telegram_worker"]


def test_every_worker_that_announces_a_file_can_reach_lms_and_the_scanner():
    """Until 0.67 the workers had no LMS variables at all, so the importer's own
    lms_scan_trigger.notify was a silent no-op on production and every download waited
    for the next folder walk to be tagged, and for the hourly scanner to be indexed."""
    compose = load_compose()
    for name in ANNOUNCING_SERVICES:
        environment = compose["services"][name]["environment"]
        for variable in (
            "MUMA_SERVER_HOSTS",
            "MUMA_SERVER_SUBSONIC_API_KEY",
            "LMS_SUBSONIC_API_KEY",
            "music_folder_path",
            "AUTH_SERVICE_URL",
            "API_KEY",
            "MUMA_API_KEY",
        ):
            assert variable in environment, f"{name} does not receive {variable}"
