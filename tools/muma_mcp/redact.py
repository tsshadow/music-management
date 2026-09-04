"""Mask secrets in container logs before they reach the agent.

Production container logs really do contain credentials -- the workers log the
environment they failed to connect with, and the LMS bridge logs its request
headers. Anything this server returns from ``prod_logs`` goes through here first.

This is best-effort and is documented as best-effort everywhere it is mentioned.
It masks the two values this server *knows* (by exact match, which is the only
part that is reliable) plus the shapes secrets usually take. A secret in a form
nobody anticipated comes through. Treat log output as sensitive regardless.
"""

from __future__ import annotations

import re
from collections.abc import Iterable

MASK = '***'

# key=value / key: value, for the usual names. The name is matched as a substring
# of the whole identifier rather than as a whole word, because the names that
# actually appear in these logs are DB_PASS and MUMA_API_KEY -- and `\bPASS\b`
# does not match inside `DB_PASS`, since an underscore is a word character. That
# over-matches slightly (`compass=north` is masked); erring that way is correct
# here. The value stops at whitespace, a quote or a comma so surrounding
# structure (JSON, a log prefix) survives.
_ASSIGNMENT = re.compile(
    r'(?i)([A-Za-z0-9_.-]*(?:password|passwd|pass|secret|token|api[_-]?key|apikey|auth[_-]?key)[A-Za-z0-9_.-]*)'
    r'(\s*[:=]\s*)'
    r'(["\']?)([^\s"\',;}]+)',
)

_BEARER = re.compile(r'(?i)\b(bearer|basic)(\s+)([A-Za-z0-9._~+/=-]{8,})')

_HEADER = re.compile(r'(?i)^(\s*(?:authorization|x-api-key|proxy-authorization)\s*:\s*)(.+)$', re.MULTILINE)

# A dsn like mysql://user:password@host/db -- the password is between : and @.
_URL_CREDENTIALS = re.compile(r'(?i)\b([a-z][a-z0-9+.-]*://[^\s:/@]+:)([^\s@]+)(@)')


def redact(text: str, secrets: Iterable[str] = ()) -> str:
    """Return ``text`` with known and probable secrets replaced by ``***``.

    ``secrets`` are literal values (the configured API key, the database
    password). They are replaced first: an exact match is the one part of this
    that cannot produce a false negative, and doing it first means a key that
    also matches a pattern is not double-processed.
    """
    if not text:
        return text

    result = text
    # Longest first, so a secret that contains another one does not leave a tail.
    for secret in sorted({s for s in secrets if s and len(s) >= 6}, key=len, reverse=True):
        result = result.replace(secret, MASK)

    result = _ASSIGNMENT.sub(lambda m: f'{m.group(1)}{m.group(2)}{m.group(3)}{MASK}', result)
    result = _BEARER.sub(lambda m: f'{m.group(1)}{m.group(2)}{MASK}', result)
    result = _HEADER.sub(lambda m: f'{m.group(1)}{MASK}', result)
    result = _URL_CREDENTIALS.sub(lambda m: f'{m.group(1)}{MASK}{m.group(3)}', result)
    return result
