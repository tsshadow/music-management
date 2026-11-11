"""Configuration for the read-only production MCP server.

The variable names here are deliberately *not* ``DB_HOST``/``DB_USER``/``DB_PASS``,
which everything else in this repository uses. Two accidents become impossible
that way:

- Those names carry the application's read/write credential. A server whose whole
  premise is "cannot write" must not be able to pick it up by inheriting an
  environment.
- A shell that sourced the repository ``.env`` points at the local, months-stale
  copy of the stack rather than at production. Confusing the two has already
  produced a confident wrong diagnosis (see the muma-prod-check skill).

Resolution fails closed and names *everything* that is missing at once, the same
contract as ``tools/db_url.py``: a server that silently defaults to some host is
how "which database did that just read" becomes a question.

Two addresses, because production publishes port 8000 on its loopback only
(issue #218) and nginx serves the two paths under different prefixes:

- ``MUMA_PROD_URL`` -- where ``/health`` is. Through nginx: ``https://<domain>``.
- ``MUMA_PROD_API_URL`` -- optional, where every ``/api/...`` call goes. Through
  nginx: ``https://<domain>/muma`` (nginx sends ``/muma/api/`` to music-manager).
  Left out, it is ``MUMA_PROD_URL``, which suits a direct ``http://<host>:8000``.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

REQUIRED = (
    'MUMA_PROD_URL',
    'MUMA_PROD_API_KEY',
    'MUMA_RO_DB_HOST',
    'MUMA_RO_DB_USER',
    'MUMA_RO_DB_PASS',
    'MUMA_RO_DB_NAME',
)

DEFAULT_CONFIG_DIR = '~/.config/muma-mcp'


class ConfigError(RuntimeError):
    """Configuration is absent or incomplete. Never raised with a value in it."""


@dataclass(frozen=True)
class Config:
    """Everything the server needs, resolved once at startup."""

    prod_url: str
    api_key: str
    db_host: str
    db_port: int
    db_user: str
    db_pass: str
    db_name: str
    # Where the /api/... calls go; empty means prod_url (see the module docstring).
    api_url: str = ''

    @property
    def api_base(self) -> str:
        """The base URL for every ``/api/...`` call: ``api_url`` when set, else ``prod_url``."""
        return self.api_url or self.prod_url

    @property
    def secrets(self) -> tuple[str, ...]:
        """The literal values that must never appear in tool output.

        Handed to ``redact`` so that a container log echoing the API key back has
        it masked by exact match rather than only by pattern.
        """
        return tuple(value for value in (self.api_key, self.db_pass) if value)


def config_path() -> Path:
    """The env file, honouring ``MUMA_MCP_CONFIG_DIR`` so tests need no home directory."""
    directory = os.getenv('MUMA_MCP_CONFIG_DIR') or DEFAULT_CONFIG_DIR
    return Path(directory).expanduser() / 'env'


def parse_env_file(text: str) -> dict[str, str]:
    """A ``KEY=VALUE`` file, without invoking a shell.

    Sourcing the file would run whatever is in it; this reads it. Blank lines and
    ``#`` comments are skipped, surrounding quotes are stripped, and a line
    without ``=`` is ignored rather than fatal -- a stray note in a config file
    should not stop the server from starting.
    """
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith('#'):
            continue
        key, sep, value = line.partition('=')
        if not sep:
            continue
        key = key.strip()
        value = value.strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in '"\'':
            value = value[1:-1]
        values[key] = value
    return values


def load(environ: dict[str, str] | None = None) -> Config:
    """Read the env file, let the real environment override it, and validate.

    The environment wins over the file so that a one-off run can point somewhere
    else without editing anything -- and so that tests never touch a real file.
    """
    env = dict(os.environ if environ is None else environ)

    path = config_path()
    if path.is_file():
        from_file = parse_env_file(path.read_text(encoding='utf-8'))
        for key, value in from_file.items():
            env.setdefault(key, value)

    missing = [name for name in REQUIRED if not env.get(name)]
    if missing:
        raise ConfigError(
            f'ontbrekende configuratie: {", ".join(missing)}. '
            f'Vul {path} (mode 600) of zet de variabelen in de omgeving. '
            'Deze server praat met productie en kent geen standaardwaarden.'
        )

    port_raw = env.get('MUMA_RO_DB_PORT', '3306')
    try:
        port = int(port_raw)
    except ValueError as exc:
        raise ConfigError(f'MUMA_RO_DB_PORT is geen getal: {port_raw!r}') from exc

    return Config(
        prod_url=env['MUMA_PROD_URL'].rstrip('/'),
        api_key=env['MUMA_PROD_API_KEY'],
        db_host=env['MUMA_RO_DB_HOST'],
        db_port=port,
        db_user=env['MUMA_RO_DB_USER'],
        db_pass=env['MUMA_RO_DB_PASS'],
        db_name=env['MUMA_RO_DB_NAME'],
        api_url=env.get('MUMA_PROD_API_URL', '').strip().rstrip('/'),
    )
