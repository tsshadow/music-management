"""The MCP entry point. The only module here that imports the SDK.

Run from the repository root, or with the root on ``PYTHONPATH``:

    python -m tools.muma_mcp

``scripts/prod/install-muma-mcp.sh`` registers it that way. Configuration is
resolved once, at startup: a server that starts without credentials and only
fails on the first tool call turns a setup mistake into a mysterious runtime one.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from tools.muma_mcp import api, db
from tools.muma_mcp.config import Config, ConfigError, load
from tools.muma_mcp.guard import QueryRejected

# In mcp 2.x FastMCP was renamed to MCPServer; `mcp.server.fastmcp` no longer
# exists. requirements-dev.txt pins the 2.x line accordingly.

# Every tool here reads. Declaring it lets a client skip the write confirmation
# it would otherwise be right to ask for -- and the claim is backed by the
# database grant, not only by this annotation.
READ_ONLY = ToolAnnotations(read_only_hint=True, destructive_hint=False)


def _load_or_exit() -> Config:
    try:
        return load()
    except ConfigError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc


CONFIG = _load_or_exit()

mcp = MCPServer('muma-prod')


def _dump(payload: Any) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, default=str)


@mcp.tool(annotations=READ_ONLY)
def prod_health() -> str:
    """De draaiende versie op productie plus de status van elke achtergrondthread.

    Dit is het eerlijkste antwoord op "wat draait er live" -- eerlijker dan een
    git-tag, die weleens bestaat voor een versie die productie nooit heeft gekregen.
    """
    return _dump(api.health(CONFIG))


@mcp.tool(annotations=READ_ONLY)
def prod_containers() -> str:
    """Naam, status en image van de muma-, database- en LMS-containers op productie."""
    return _dump(api.containers(CONFIG))


@mcp.tool(annotations=READ_ONLY)
def prod_logs(name: str, tail: int = 200) -> str:
    """De staart van het log van één productiecontainer, met secrets gemaskeerd.

    Gebruik prod_containers voor de geldige namen. Maskering is best-effort:
    behandel de output als gevoelig.
    """
    return api.logs(CONFIG, name, tail)


@mcp.tool(annotations=READ_ONLY)
def prod_tables() -> str:
    """Alle tabellen in de productiedatabase. Goedkoop; gebruik dit voor je SQL gokt."""
    return _dump(db.list_tables(CONFIG))


@mcp.tool(annotations=READ_ONLY)
def prod_describe(table: str) -> str:
    """De kolommen, types en sleutels van één tabel op productie."""
    try:
        return _dump(db.describe(CONFIG, table))
    except QueryRejected as exc:
        return f'geweigerd: {exc}'


@mcp.tool(annotations=READ_ONLY)
def prod_query(sql: str, limit: int = 100) -> str:
    """Voer één read-only SQL-statement uit op de productiedatabase.

    Toegestaan zijn SELECT, WITH, SHOW, DESCRIBE en EXPLAIN, één statement per
    aanroep. Het account heeft alleen SELECT-rechten, dus schrijven is niet
    mogelijk -- ook niet als je het probeert. Er wordt geen LIMIT toegevoegd aan
    je query; er worden maximaal `limit` rijen teruggegeven en het antwoord zegt
    het als er is afgekapt.
    """
    try:
        return _dump(db.run_query(CONFIG, sql, limit))
    except QueryRejected as exc:
        return f'geweigerd: {exc}'


def main() -> None:
    mcp.run()


if __name__ == '__main__':
    main()
