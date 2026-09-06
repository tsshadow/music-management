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
    whatever DNS the host has. On the office LAN ``lms`` resolves to
    192.0.2.27, so a container started without LMS configuration called
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
