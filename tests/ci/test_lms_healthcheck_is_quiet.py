"""The production LMS healthcheck must ask a question LMS answers without logging an error.

It used to call `/rest/ping.view` without credentials. LMS answered 400 -- fine for a
liveness probe -- but also logged `[API_SUBSONIC] Error while processing request ...
Required parameter 'c' is missing` for every probe: an ERROR every 30 seconds, 2,880 a
day, burying the lines that matter in `docker logs lms`. The probe now calls an endpoint
the Subsonic router declares `AuthenticationMode::Unauthenticated`, with the client
parameters it requires, so it answers 200 and logs nothing.
"""

import re
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parents[2]
COMPOSE = REPO_ROOT / "services" / "music-management-server" / "docker-compose.yml"
SUBSONIC_ROUTER = (
    REPO_ROOT / "services" / "music-management-server" / "src" / "libs" / "subsonic" / "impl" / "SubsonicResource.cpp"
)


def healthcheck_command() -> str:
    """The shell command of the lms service's healthcheck."""
    test = yaml.safe_load(COMPOSE.read_text())["services"]["lms"]["healthcheck"]["test"]
    return test[1] if test[0] == "CMD-SHELL" else " ".join(test[1:])


def test_the_healthcheck_calls_an_unauthenticated_subsonic_endpoint():
    match = re.search(r"/rest(/\w+)\.view\?(\S+?)'", healthcheck_command())
    assert match, "the LMS healthcheck no longer calls a /rest/<endpoint>.view URL with parameters"
    endpoint, query = match.groups()
    unauthenticated = re.findall(
        r'\{ "(/\w+)", \{ \w+, AuthenticationMode::Unauthenticated \} \}', SUBSONIC_ROUTER.read_text()
    )
    assert endpoint in unauthenticated, (
        f"{endpoint} needs credentials, so every probe logs an ERROR; use one of {unauthenticated}"
    )
    assert "c=" in query and "v=" in query, "without c= and v= LMS logs 'Required parameter ... is missing'"
