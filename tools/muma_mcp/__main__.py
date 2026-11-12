"""The MCP entry point. The only module here that imports the SDK.

Run from the repository root, or with the root on ``PYTHONPATH``:

    python -m tools.muma_mcp

``install-muma-mcp.sh`` registers it that way. Configuration is
resolved once, at startup: a server that starts without credentials and only
fails on the first tool call turns a setup mistake into a mysterious runtime one.
"""

from __future__ import annotations

import json
import sys
from typing import Any

from mcp.server.mcpserver import MCPServer
from mcp.types import ToolAnnotations

from tools.muma_mcp import api, db, hosts
from tools.muma_mcp.config import Config, ConfigError, load
from tools.muma_mcp.guard import QueryRejected
from tools.muma_mcp.hosts import HostError, HostsConfig

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


def _load_hosts_or_exit() -> HostsConfig:
    try:
        return hosts.load()
    except HostError as exc:
        print(str(exc), file=sys.stderr)
        raise SystemExit(2) from exc


HOSTS = _load_hosts_or_exit()

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
    """Name, status and image of the muma, database and LMS containers on production."""
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


# --- homelab hosts through muma-ro (issue #176) ------------------------------------------------
# Each call is one muma-ro verb on the host; the host's policy decides what is allowed and
# answers "refused: <reason>" otherwise. `host` is prod, devvm, runner, nas or proxmox.


def _on(host: str, build: Any) -> str:
    """Build the command, run it on `host`, and turn a configuration problem into text."""
    try:
        return hosts.run_on(HOSTS, host, build())
    except HostError as exc:
        return f'refused: {exc}'


@mcp.tool(annotations=READ_ONLY)
def host_help(host: str) -> str:
    """The verbs, roots, containers and units muma-ro allows on one host."""
    return _on(host, lambda: 'help')


@mcp.tool(annotations=READ_ONLY)
def host_ls(host: str, path: str, long: bool = False) -> str:
    """List a directory under one of the host's roots."""
    return _on(host, lambda: hosts.cmd_ls(path, long))


@mcp.tool(annotations=READ_ONLY)
def host_stat(host: str, path: str) -> str:
    """stat of a file or directory under one of the host's roots."""
    return _on(host, lambda: f'stat {hosts.quote(path)}')


@mcp.tool(annotations=READ_ONLY)
def host_find(host: str, path: str, maxdepth: int = 1, type: str | None = None, name: str | None = None) -> str:  # noqa: A002  # pylint: disable=redefined-builtin
    """find under a root: depth 0 to 3, type f or d, and a name pattern such as *.nfo."""
    return _on(host, lambda: hosts.cmd_find(path, maxdepth, type, name))


@mcp.tool(annotations=READ_ONLY)
def host_head(host: str, path: str, lines: int = 50) -> str:
    """The first lines of a text file (.nfo, .txt, .log and the like) under a read root."""
    return _on(host, lambda: hosts.cmd_head(path, lines))


@mcp.tool(annotations=READ_ONLY)
def host_du(host: str, path: str) -> str:
    """The size of a directory under a root (du -s). Can take up to two minutes."""
    return _on(host, lambda: f'du -s {hosts.quote(path)}')


@mcp.tool(annotations=READ_ONLY)
def host_df(host: str) -> str:
    """Free disk space on every mounted file system of the host."""
    return _on(host, lambda: 'df -h')


@mcp.tool(annotations=READ_ONLY)
def host_containers(host: str) -> str:
    """Every container on the host: name, image, status, created."""
    return _on(host, lambda: 'docker ps -a')


@mcp.tool(annotations=READ_ONLY)
def host_container_logs(host: str, name: str, tail: int = 200, since: str | None = None) -> str:
    """The tail of a container's log, masked. since looks like 30m, 2h or 1d."""
    return _on(host, lambda: hosts.cmd_container_logs(name, tail, since))


@mcp.tool(annotations=READ_ONLY)
def host_container_inspect(host: str, name: str) -> str:
    """State, health, restart count, image and mounts of a container. Never its environment."""
    return _on(host, lambda: f'docker inspect {hosts.name(name, "container")}')


@mcp.tool(annotations=READ_ONLY)
def host_container_env(host: str, name: str, key: str) -> str:
    """One environment variable of a container, from the host's list of keys that hold no secret.

    For a music-manager setting, GET /api/config first: a value saved in Beheer wins over the
    environment.
    """
    return _on(host, lambda: f'docker exec {hosts.name(name, "container")} printenv {hosts.name(key, "key")}')


@mcp.tool(annotations=READ_ONLY)
def host_unit_status(host: str, unit: str) -> str:
    """systemctl status of a listed unit, such as muma-db-backup.service."""
    return _on(host, lambda: f'systemctl status {hosts.name(unit, "unit")}')


@mcp.tool(annotations=READ_ONLY)
def host_journal(host: str, unit: str, lines: int = 200) -> str:
    """The last journal lines of a listed unit, masked."""
    return _on(host, lambda: hosts.cmd_journal(unit, lines))


@mcp.tool(annotations=READ_ONLY)
def nas_datasets(dataset: str | None = None) -> str:
    """ZFS datasets on the NAS: used, available, referenced, mount point."""
    return _on('nas', lambda: 'zfs list' + (f' {hosts.name(dataset, "dataset")}' if dataset else ''))


@mcp.tool(annotations=READ_ONLY)
def nas_snapshots(dataset: str) -> str:
    """The snapshots of one dataset on the NAS."""
    return _on('nas', lambda: f'zfs list -t snapshot {hosts.name(dataset, "dataset")}')


@mcp.tool(annotations=READ_ONLY)
def nas_pool_status() -> str:
    """zpool status of every pool on the NAS."""
    return _on('nas', lambda: 'zpool status')


@mcp.tool(annotations=READ_ONLY)
def nas_acl(path: str) -> str:
    """The access control list of a path on the NAS (getfacl)."""
    return _on('nas', lambda: f'getfacl {hosts.quote(path)}')


@mcp.tool(annotations=READ_ONLY)
def pve_list() -> str:
    """Every container and VM on the Proxmox node, with its state."""
    return _on('proxmox', lambda: 'pct list') + '\n' + _on('proxmox', lambda: 'qm list')


@mcp.tool(annotations=READ_ONLY)
def pve_config(ctid: int, vm: bool = False) -> str:
    """The configuration of a listed container (or VM), without description, passwords and keys."""
    return _on('proxmox', lambda: f'{"qm" if vm else "pct"} config {hosts.number(ctid, "ctid", 100, 999_999_999)}')


@mcp.tool(annotations=READ_ONLY)
def pve_backup_log(file: str) -> str:
    """The last 200 lines of one backup log in /var/log/vzdump on the Proxmox node."""
    return _on('proxmox', lambda: f'vzdump-log {hosts.name(file, "file")}')


@mcp.tool(annotations=READ_ONLY)
def pve_relay(ctid: int, verb: str, args: str = '') -> str:
    """Run one muma-ro verb inside a listed container, through the Proxmox node.

    The container's own muma-ro and policy decide; `verb` and `args` are what you would write
    on that host, for example verb='df', args='-h'. Quote a path with single quotes.
    """
    return _on('proxmox', lambda: hosts.cmd_relay(ctid, f'{verb} {args}'.strip()))


@mcp.tool(annotations=READ_ONLY)
def portainer_get(path: str) -> str:
    """GET a Portainer API path under /api/endpoints or /api/stacks, as a view-only user."""
    try:
        return hosts.portainer_get(HOSTS, path)
    except HostError as exc:
        return f'refused: {exc}'


@mcp.tool(annotations=READ_ONLY)
def gitlab_get(path: str) -> str:
    """GET a GitLab API v4 path: /projects/:id/pipelines, jobs, merge_requests, issues, or /runners."""
    try:
        return hosts.gitlab_get(HOSTS, path)
    except HostError as exc:
        return f'refused: {exc}'


@mcp.tool(annotations=READ_ONLY)
def pve_get(path: str) -> str:
    """GET a Proxmox API path under /nodes, /cluster/resources, /cluster/backup, /cluster/status or /version."""
    try:
        return hosts.pve_get(HOSTS, path)
    except HostError as exc:
        return f'refused: {exc}'


def main() -> None:
    mcp.run()


if __name__ == '__main__':
    main()
