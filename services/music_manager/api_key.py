"""Resolution and comparison of the system API key.

Every router used to spell the key out itself:

    API_KEY = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY') or '<a literal uuid>'

That literal was the deployment's real ``MUMA_API_KEY``, committed in ten router
modules and thirteen test modules. Presenting it as ``X-API-Key`` resolves to
``{'type': 'system'}``, and ``rbac.has_permission`` / ``rbac.is_admin_auth`` grant
that identity *every* permission plus the admin role -- so read access to this
repository was read/write admin access to the API.

Resolution now fails closed. With neither variable set there is no system key at
all: ``is_system_api_key`` returns False for everything, and ``X-API-Key`` falls
through to the per-user token lookup in ``routers.users.verify_token``. A missing
key can therefore only cost service-to-service calls their access; it can never
hand it to someone who read the source.

The environment is read per call rather than captured at import, so a value set
after this module is first imported (as the test suite does) still takes effect.
"""

import logging
import os
import secrets

logger = logging.getLogger('music-manager')

_MISSING_KEY_WARNING_EMITTED = False


def resolve_system_api_key() -> str | None:
    """Return the configured system API key, or None when none is configured.

    ``API_KEY`` wins over ``MUMA_API_KEY``; both being unset or empty means the
    deployment has no system key, which is a valid (if degraded) state rather
    than an error -- user tokens keep working.
    """
    key = os.getenv('API_KEY') or os.getenv('MUMA_API_KEY')
    if key:
        return key

    global _MISSING_KEY_WARNING_EMITTED  # noqa: PLW0603 -- warn once per process, not per request
    if not _MISSING_KEY_WARNING_EMITTED:
        _MISSING_KEY_WARNING_EMITTED = True
        logger.warning(
            'Neither API_KEY nor MUMA_API_KEY is set: service-to-service calls '
            'presenting the system key will be rejected. User API keys are unaffected.'
        )
    return None


def is_system_api_key(candidate: str | None) -> bool:
    """Whether ``candidate`` is the configured system API key.

    Compared with ``secrets.compare_digest`` so that a wrong key takes the same
    time to reject however much of it is right.
    """
    key = resolve_system_api_key()
    if not key or not candidate:
        return False
    return secrets.compare_digest(candidate, key)
