"""Where LMS is, and what to authenticate to it with.

One place, because there used to be two and only one of them was fed.

``lms_subsonic.py`` read ``LMS_URL`` / ``LMS_HOSTS`` / ``MUMA_SERVER_HOSTS`` from the
environment and the radio scheduler worked. ``LmsScanTrigger`` read ``lms_hosts`` and
``lms_subsonic_api_key`` out of the ConfigStore, and nothing in
``docker/docker-compose.yml`` sets ``LMS_HOSTS`` -- the line is commented out -- so on a
deployment where nobody typed a host into the settings page the whole scan trigger was a
no-op. Silently: the send path returned early without a log line, so a library that never
picked up a moved folder looked like an LMS problem.

The ConfigStore still wins when it holds a value; that is the settings page doing its job.
The environment is the fallback rather than the other way round, for the same reason.
"""

import os
import re

# A URL with a query string, as it appears inside an error message: absolute, or the bare
# path urllib3 puts after "with url:" in a connection error ("Max retries exceeded with
# url: /rest/x.view?apiKey=..."). The query is cut at whitespace or a quote, which is
# where requests' messages end a URL.
_URL_WITH_QUERY = re.compile(r'''(https?://[^\s?'"<>]+|\burl: /[^\s?'"<>]*)\?[^\s'"<>]*''')

#: The environment variables that name an LMS host, most specific first. Shared with the
#: Subsonic client so that configuring one configures both.
HOST_ENV_NAMES = ('LMS_URL', 'LMS_HOSTS', 'MUMA_SERVER_HOSTS')

#: Likewise for the Subsonic API key. compose passes both spellings through, because the
#: two consumers were written a year apart.
API_KEY_ENV_NAMES = ('MUMA_SERVER_SUBSONIC_API_KEY', 'LMS_SUBSONIC_API_KEY')


class LmsNotConfigured(RuntimeError):
    """No LMS address is configured, so there is nothing safe to call."""


def lms_base_url() -> str:
    """Where to reach LMS, from the environment. Never guessed.

    This used to fall back to a hardcoded ``http://lms:5082``. On the deployment
    that is right -- ``lms`` is the container_name of the separately deployed LMS
    stack, on the shared ``music-management_db`` network -- and that is exactly
    what made it dangerous everywhere else: a bare hostname is resolved by
    whatever DNS the host has. On the owner's LAN ``lms`` resolves to
    the production host, so a container started without LMS configuration called
    *production* every five seconds, and neither end said so. Production's LMS
    logs the rejection without a client address, so it reads as a fault in
    production's own radio thread; it took reading the reverse proxy's access log
    to see the requests were coming from a developer workstation.

    ``MUMA_SERVER_HOSTS`` is read as well, because that is the variable compose
    actually sets for this service (``docker/docker-compose.yml``, with a comment
    explaining the ``lms:5082`` value). The old code did not read it, so the
    deployment was working by coincidence: the hardcoded default happened to
    equal the configured value.

    Raises ``LmsNotConfigured`` when nothing is set, so an unconfigured environment
    produces one clear message per attempt instead of silent traffic to someone
    else's server.
    """
    for name in HOST_ENV_NAMES:
        url = (os.getenv(name) or '').split(',')[0].strip()
        if url:
            return normalise_host(url)

    raise LmsNotConfigured(
        'No LMS address configured: set LMS_URL, LMS_HOSTS or MUMA_SERVER_HOSTS. '
        'There is deliberately no default -- a bare hostname like "lms" resolves '
        'through the host DNS and has reached production from a developer machine.'
    )


def normalise_host(host: str) -> str:
    """A host may bring its own scheme; a bare one is plain HTTP.

    LMS sits on the container network next to muma, so unencrypted is the default on
    purpose -- but the setting is free text, and somebody who puts an https URL in it
    means it, and used to get ``http://https://...`` for their trouble.
    """
    url = host.strip()
    if not url.startswith(('http://', 'https://')):
        url = 'http://' + url
    return url.rstrip('/')


def lms_api_key() -> str:
    """The Subsonic API key from the environment, or an empty string."""
    for name in API_KEY_ENV_NAMES:
        key = (os.getenv(name) or '').strip()
        if key:
            return key
    return ''


def redact_url(text: str) -> str:
    """`text` with the query string of every http(s) URL in it replaced by ``?<redacted>``.

    Subsonic authenticates in the query string (``apiKey=...``), and requests puts the
    full URL into both ``HTTPError`` ("... for url: http://lms/rest/x?apiKey=...") and
    connection errors. Logged at WARNING, that went into the events table and out to
    ntfy. Use this on any error or URL from an LMS call before it is logged.
    """
    return _URL_WITH_QUERY.sub(r'\1?<redacted>', str(text))


def resolve_lms_api_key(store=None) -> str:
    """The Subsonic API key every LMS caller uses: the ConfigStore first, then the environment.

    `lms_subsonic_api_key` in the store is a key typed on the config page when there is
    one, else `LMS_SUBSONIC_API_KEY` from the environment (see ConfigStore's
    precedence). Only when that is empty are the environment names read directly.

    The radio scheduler used to read the environment only while ``LmsScanTrigger`` read
    the store first, so the two could authenticate with different keys and a fix made
    on one path did not reach the other. `store` is injectable for tests; a value that
    is not a string (a mocked store) counts as unset.
    """
    if store is None:
        try:
            from services.common.config_store import ConfigStore

            store = ConfigStore()
        except Exception:
            store = None
    configured = ''
    if store is not None:
        try:
            value = store.get('lms_subsonic_api_key')
        except Exception:
            value = None
        if isinstance(value, str):
            configured = value.strip()
    return configured or lms_api_key()
