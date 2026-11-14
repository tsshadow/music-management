# Read-Only Agent Access: Technical Design

Implements [functional.md](functional.md), with the decisions of 2026-11-12 listed there. Five hosts get an SSH account `muma-ro` whose key is
forced to run `/usr/local/bin/muma-ro`. That program parses `$SSH_ORIGINAL_COMMAND` against the
host's policy and runs the matching command with `execve`, never through a shell. Portainer and
GitLab get read-only API tokens. `tools/muma_mcp` gets the tools that call both.

Host names in this document are placeholders (`prod.example.com`, `192.0.2.x`).

## Hosts

| Host | Route | Host class (policy) | First use |
|---|---|---|---|
| Production | SSH, `muma-ro` | `prod` | the library, the import queue, container settings, timers |
| Dev VM | SSH, `muma-ro` | `devvm` | the same view of the local stack |
| CI runner on the workstation | none while agents run there as the local user (decision 6) | `runner` | job containers, disk, runner service |
| CI runner LXC | through the Proxmox relay (below) | `runner` | the same |
| NAS | SSH, `muma-ro` | `nas` | datasets, snapshots, pool health, ACLs on the music tree |
| Proxmox node | SSH, `muma-ro` | `proxmox` | container limits, backup jobs, the relay into LXCs |
| Portainer | API token, read-only user | none | stacks, containers, logs |
| GitLab | API token, `read_api` scope | none | pipelines, jobs, runners, MRs, issues |

The LXCs are not reached by SSH. The Proxmox wrapper has one verb that runs the container's own
`muma-ro` through `pct exec`, so the container's own policy decides (see Relay).

## Account and Key

- A system account `muma-ro` with no password and no `sudo` group. It is not in the `docker`
  group: Docker access is root-equivalent (issue #176). Its login shell is `/bin/sh`, because
  sshd starts the forced command through the login shell. The shell never sees the agent's text:
  `command=` replaces it, and the text arrives only in `SSH_ORIGINAL_COMMAND`.
- One `authorized_keys` line per client key:

  ```
  restrict,command="/usr/local/bin/muma-ro --key <key name>",from="<client address>" ssh-ed25519 AAAA... <key name>
  ```

  `restrict` turns off port, agent and X11 forwarding and the TTY. `--key` puts the key's name in
  every log line, so a removed or misused key is easy to find. `from=` limits the key to the
  address of the machine that runs the MCP server.
- One key pair per host (decision 2): `~/.ssh/muma-ro-<class>_ed25519` on the machine that runs
  the MCP server (mode 0600). This repository
  and its docs name it only. The agent's permission rules deny reads of `~/.ssh/`. Only the MCP
  server process uses the key.
- Host keys are pinned: the MCP server connects with `StrictHostKeyChecking=yes` and its own
  `known_hosts` file under `~/.config/muma-mcp/`.

## The Wrapper: `tools/muma_ro/`

Python 3.9 or later, standard library only. The install script builds one zipapp from the
package and copies it to `/usr/local/lib/muma-ro/muma-ro.pyz`. `/usr/local/bin/muma-ro` and
`/usr/local/libexec/muma-ro-priv` are two small launchers of that file. All three are owned by
root.

| Module | Purpose |
|---|---|
| `parse.py` | Turns the command string into a verb and typed arguments, or a refusal with a reason |
| `policy.py` | Loads and checks `/etc/muma-ro/policy.json` |
| `verbs.py` | One spec per verb: allowed flags, argument kinds, the fixed `argv` template, time limit, privilege |
| `run.py` | Runs the `argv` with a time limit and an output cap, then masks secrets |
| `audit.py` | Writes the log line |
| `cli.py` | The two entry points and the self-test |

The zipapp also holds `tools/muma_mcp/redact.py`, so the host masks secrets with the same code as
the MCP server, without a second copy in the repository.

### Parsing

1. No `SSH_ORIGINAL_COMMAND`, or an empty one: refuse with "no command" (an interactive login).
2. Longer than 4096 bytes, or a NUL, CR or LF in it: refuse.
3. Scan the string character by character, tracking single quotes. Outside single quotes, every
   character must be in `[A-Za-z0-9 _./:=@+,%-]`. That refuses the separators (`;`, `|`, `&`),
   substitution (`$`, the backtick), redirection (`<`, `>`), grouping and globbing
   (`( ) { } [ ] * ?`), and `!`, `#`, `~`, `"` and `\`. Inside single quotes any printable character is allowed, but the quoted token may only fill a
   `path` or `glob` argument (decision 1). A double quote or a backslash anywhere
   is refused.
4. Split into tokens. The first token is the verb, and it must be enabled in the host's policy.
5. Match the rest against the verb's spec. Each flag is an exact token from the spec. Each
   argument has a kind:

   | Kind | Check |
   |---|---|
   | `path` | No `..` component. `os.path.realpath` (follows symbolic links) is a root of the policy, or below it as `root + "/"`, so `/mnt/musicx` does not pass as `/mnt/music`. The root's mode allows the verb (`list` or `read`). |
   | `int` | Digits only, at most the spec's maximum (for example `tail` 2000, `maxdepth` 3). |
   | `container` | In the policy's container list, or matches one of its name patterns. |
   | `env_key` | In the policy's key list. |
   | `unit` | In the policy's unit list. |
   | `dataset` | Equal to or below a dataset prefix in the policy. |
   | `ctid` | In the policy's container id list. |
   | `glob` | Printable, at most 128 characters, no `/`. Used only by `find -name`. |
   | `duration` | `[0-9]+[smhd]`, for `--since`. |

6. Build the `argv` from the verb's template: an absolute binary path, fixed flags first, then the
   checked arguments, with `--` before paths where the tool supports it. A flag the agent did not
   send is never added from its text.

A refusal exits with code 2 and one line `muma-ro: refused: <reason>` on stderr.

### Running

- `subprocess.run(argv, shell=False, stdin=DEVNULL)` with a minimal environment
  (`PATH=/usr/sbin:/usr/bin:/sbin:/bin`, `LC_ALL=C.UTF-8`).
- A time limit per verb: 30 s by default, 120 s for `du` and `find`. On timeout the process
  group is killed and the output so far is returned with "timed out after N s", exit code 124.
- Output is cut at 1 MiB with a last line that says so.
- Logs (`docker logs`, `journalctl`) go through `redact.py` before they are written to stdout.

### Privileged verbs

Docker, `pct`, `qm` and some `zfs` and `journalctl` calls need root. `muma-ro` does not run them
itself. It calls `sudo -n /usr/local/libexec/muma-ro-priv --key <name>` with the original string,
and the helper parses the string again with the same code and the same root-owned policy before it
runs anything. The sudoers drop-in is one line:

```
muma-ro ALL=(root) NOPASSWD: /usr/local/libexec/muma-ro-priv
```

So a bug in the unprivileged path cannot widen what runs as root: the helper refuses on its own.

### Policy

`/etc/muma-ro/policy.json`, root 0644, written by the install script from
`tools/muma_ro/policies/<class>.example.json` plus the host's values. The repository keeps only the
example files, with placeholder paths and names.

```json
{
  "class": "prod",
  "verbs": ["ls", "stat", "find", "head", "du", "df", "free", "uptime",
            "docker-ps", "docker-logs", "docker-inspect", "docker-stats", "docker-system-df",
            "docker-printenv", "systemctl-status", "systemctl-timers", "journalctl"],
  "roots": [
    {"path": "/mnt/music", "mode": "read"},
    {"path": "/mnt/backups/muma", "mode": "list"}
  ],
  "containers": ["music-manager", "muma-bpm-analyzer"],
  "container_patterns": ["^music-management-[a-z0-9-]+$"],
  "env_keys": ["import_folder_path", "eps_folder_path"],
  "units": ["muma-db-backup.service", "muma-db-backup-stale.service", "muma-db-restore-check.service"],
  "head_extensions": [".nfo", ".txt", ".json", ".m3u", ".sfv", ".cue", ".log"]
}
```

`policy.py` refuses to load a policy that has `/` as a root, a root under `/etc`, `/root`,
`/home/*/.ssh` or `/var/lib/docker`, or an `env_keys` entry that matches
`PASS|SECRET|TOKEN|KEY$|_KEY_|PRIVATE` (case-insensitive). A refused policy refuses every command,
so a bad edit fails closed. Mode `list` allows `ls`, `stat`, `find` and `du`. Mode `read` also
allows `head` of a file with a listed extension. The backup root is `list` because a database dump
holds every API key and password hash of the installation.

Note on settings: `docker-printenv` returns what a container was started with. A setting changed in
Beheer lives in music-manager's `config.json` and wins over the environment (AGENTS.md, Runtime
Configuration). The MCP tool for a setting therefore reads `GET /api/config` first, where secrets
already come back as the sentinel, and uses `printenv` for the containers that have no such API.

## Verbs Per Host Class

| Verb (agent writes) | Runs | prod | devvm | runner | nas | proxmox |
|---|---|---|---|---|---|---|
| `ls [-l] [-a] PATH` | `/usr/bin/ls -1 [--] PATH` | yes | yes | yes | yes | yes |
| `stat PATH` | `/usr/bin/stat -- PATH` | yes | yes | yes | yes | yes |
| `find PATH [-maxdepth N≤3] [-type f\|d] [-name GLOB]` | `/usr/bin/find PATH -maxdepth N ...`; no `-exec`, `-delete`, `-fprint`, `-ok` exist in the grammar | yes | yes | yes | yes | no |
| `head [-n N≤200] PATH` | `/usr/bin/head -n N -- PATH`, read-mode root and listed extension | yes | yes | no | no | no |
| `du -s PATH` | `/usr/bin/du -s -- PATH`, 120 s | yes | yes | yes | yes | no |
| `df [-h] [PATH]`, `free -m`, `uptime` | fixed | yes | yes | yes | yes | yes |
| `docker ps [-a]` | fixed `--format` (name, image, status, created) | yes | yes | yes | no | no |
| `docker logs --tail N≤2000 [--since D] C` | never `-f`; redacted | yes | yes | yes | no | no |
| `docker inspect C` | fixed `--format`: state, health, restart count, image, mounts. Never `Config.Env` | yes | yes | yes | no | no |
| `docker stats`, `docker system df` | `--no-stream`, fixed format | yes | yes | yes | no | no |
| `docker exec C printenv KEY` | `docker exec C printenv KEY`, key from the list | yes | yes | no | no | no |
| `systemctl status UNIT`, `systemctl list-timers` | `--no-pager --lines=20` | yes | yes | yes | no | yes |
| `journalctl -u UNIT [-n N≤500] [--since D]` | redacted | yes | yes | yes | no | yes |
| `zfs list [-t snapshot] [DATASET]`, `zfs get PROP DATASET` | fixed `-o` columns; properties from a list | no | no | no | yes | no |
| `zpool status [-x]`, `zpool list` | fixed | no | no | no | yes | no |
| `getfacl PATH` | `/usr/bin/getfacl -- PATH` | no | no | no | yes | no |
| `pct list`, `qm list`, `pvesm status` | fixed | no | no | no | no | yes |
| `pct config ID`, `qm config ID` | output without `description`, `cipassword`, `sshkeys` lines | no | no | no | no | yes |
| `vzdump-log FILE` | `tail -n 200` of a file in `/var/log/vzdump/` | no | no | no | no | yes |
| `pct exec ID -- COMMAND` | relay, below | no | no | no | no | yes |
| `help` | prints the host's enabled verbs and roots | yes | yes | yes | yes | yes |

Never on any host: a shell, an interpreter, `cat` of an arbitrary file, `docker exec` other than
`printenv`, `docker run`, `docker cp`, `zfs` or `zpool` verbs that change state, `midclt`, `pvesh`,
`qm`/`pct` verbs other than those above, and any path under `/etc/gitlab-runner`, which holds the
runner token (bug report 077).

### Relay

`pct exec <ctid> -- <command>` on the Proxmox node runs
`pct exec <ctid> -- /usr/local/bin/muma-ro --key relay-<node key name> --command '<command>'` as
root through the helper. The container has its own `muma-ro` and its own policy; `--command` takes
the place of `SSH_ORIGINAL_COMMAND`. The node checks only that `<ctid>` is on its list and that
the inner string passes step 3 of the parser. The container decides the rest and logs it.

### Proxmox API

Besides the relay, the Proxmox MCP tools read node and backup state through the Proxmox API with a
token whose role is `PVEAuditor` (decision 5): `MUMA_PVE_URL` and `MUMA_PVE_RO_TOKEN`, GET only.

## Logging

One line per request to syslog (`LOG_AUTH`, tag `muma-ro`), so journald keeps it and the
`muma-ro` account cannot change it:

```json
{"ts": "2026-11-12T14:31:07Z", "key": "workstation", "client": "192.0.2.10", "class": "prod",
 "argv0": "ls", "command": "ls -l /mnt/music/EPs", "decision": "allowed", "reason": null,
 "exit": 0, "bytes": 18234, "ms": 41}
```

The command is cut at 512 characters and passed through `redact.py`. The output is never logged.
The helper logs too, so a privileged command has two lines.

## MCP Tools

`tools/muma_mcp/hosts.py`: plain Python with no SDK, like the rest of the package (its
`__init__.py` says why). It runs

```
ssh -i ~/.ssh/muma-ro-<class>_ed25519 -o BatchMode=yes -o IdentitiesOnly=yes \
    -o StrictHostKeyChecking=yes -o UserKnownHostsFile=~/.config/muma-mcp/known_hosts \
    -T muma-ro@<host> -- <command string>
```

with a 60 s client time limit, and returns stdout, stderr and the exit code. The command string is
built by the tool from typed arguments, with `shlex.quote` on paths and globs, so the agent never
writes a raw command. The client checks step 3 of the parser too, so a refusal comes back before a
connection is made.

Configuration, added to the env file of `tools/muma_mcp/config.py` (names only, values by the
person):

| Variable | Meaning |
|---|---|
| `MUMA_RO_SSH_KEY_DIR` | directory with `muma-ro-<class>_ed25519` per host (default `~/.ssh`) |
| `MUMA_RO_HOSTS` | `prod=muma-ro@prod.example.com,devvm=...,runner=...,nas=...,proxmox=...` |
| `MUMA_PORTAINER_URL`, `MUMA_PORTAINER_RO_TOKEN` | Portainer API and the read-only token |
| `MUMA_GITLAB_URL`, `MUMA_GITLAB_RO_TOKEN` | GitLab API and the `read_api` token |

These are optional. A missing host disables its tools and leaves the existing six working.

Tools, all `READ_ONLY` annotated:

- `host_help(host)`, `host_ls(host, path, long=False)`, `host_stat(host, path)`,
  `host_find(host, path, maxdepth=1, type=None, name=None)`, `host_head(host, path, lines=50)`,
  `host_du(host, path)`, `host_df(host)`.
- `host_containers(host)`, `host_container_logs(host, name, tail=200, since=None)`,
  `host_container_inspect(host, name)`, `host_container_env(host, name, key)`.
- `host_unit_status(host, unit)`, `host_journal(host, unit, lines=200)`.
- `nas_datasets(dataset=None)`, `nas_snapshots(dataset)`, `nas_pool_status()`, `nas_acl(path)`.
- `pve_list()`, `pve_config(ctid)`, `pve_backup_log(file)`, `pve_relay(ctid, verb, ...)`.
- `portainer_get(path)` and `gitlab_get(path)`: GET only, path from an allowlist of prefixes
  (`/api/endpoints`, `/api/stacks` for Portainer; `/projects/:id/pipelines`, `/jobs`, `/runners`,
  `/merge_requests`, `/issues` for GitLab).

All output goes through `redact.py` with the configured secrets, as `prod_logs` does today.

## Portainer and GitLab

Neither gets the wrapper.

- **Portainer.** An access token carries the rights of the user who made it. The person makes a
  separate user with a view-only role on the environments and makes the token as that user
  (decision 4). The check: a stop call on a throwaway container with that token is refused. The
  existing Portainer MCP tools that restart, stop or redeploy are removed from agent sessions.
- **GitLab.** For the MCP tools only (decision 3), a token with the `read_api` scope only, from a separate bot user or as a project
  access token with the Reporter role. The check: `POST /projects/:id/issues` with that token is
  refused. For the GitLab host's own disk and containers, the Proxmox relay reaches its LXC.

## Installation

`scripts/muma-ro/install.sh --class <class> --key-name <name> --pubkey <file> --client <address>`
prints every change and does nothing. `--apply` makes them; `--uninstall` removes them. A person
runs it on each host. An agent never does (issue #176).

It checks Python 3.9 or later, then creates the account, installs the zipapp and both launchers,
writes the policy, writes the sudoers drop-in and checks it with `visudo -c`, and adds the
`authorized_keys` line. It ends with `muma-ro --self-test`: every enabled verb once with a harmless
argument, and a fixed list of commands that must be refused. A self-test failure undoes the install.

## Rollout

1. MR: `tools/muma_ro/` with the parser tests, the `prod` example policy, the install script and
   the MCP tools for `prod`.
2. A person installs on production: dry run, `--apply`, self-test.
3. One week on production. Exit criteria: the parser tests are green in CI, the log of the week
   has no allowed command outside the verb table, and the agent answered one real question (for
   example the import queue of #51) without pasted output.
4. Then, one host at a time, each with its own policy and self-test: the dev VM, the CI runner,
   the NAS, the Proxmox node with the relay (last, because its helper reaches every container),
   and through the relay the CI runner LXC and the GitLab LXC.
5. Portainer and GitLab tokens are independent of the wrapper and can come at any step.

## Data Model

None.

## API Contract

No application API changes. The contract is the command grammar of the verb table, served by
`help` on each host.

## Cross-App Impact

None for the apps. `tools/muma_mcp` gets new optional tools and config. `docker/Dockerfile.tools`
copies `tools/muma_mcp`, and `hosts.py` adds nothing the tools image runs.

## Technical Acceptance Criteria

1. Parser tests (`tools/test_muma_ro_parse.py`) refuse, each with its own reason:
   - paths: `..` in any position, `/mnt/music/../etc`, `/mnt/musicx`, a symbolic link under a root
     that points outside it, a relative path, a path under a `list` root for `head`;
   - verbs: `sh`, `bash`, `python3`, `rm`, `cat`, `docker run`, `docker exec C sh`,
     `docker exec C printenv` without a key, `docker logs -f`, `find -exec`, `find -delete`,
     `zfs destroy`, `pct set`, `pvesh`;
   - characters: `;`, `|`, `&&`, `$(...)`, a backtick, `>`, `<`, a newline, a NUL, a double quote,
     a backslash, a quoted token in a non-path position;
   - values: `tail` 2001, `maxdepth` 4, an `env_key` not on the list, a command of 4097 bytes, an
     empty command.
2. The same tests accept a quoted path such as `'/mnt/music/EPs/Artist & Artist (Live)'` under a
   root, and the resulting `argv` has the path as one element.
3. A test checks that no module of `tools/muma_ro` calls `shell=True`, `os.system`, `os.popen` or
   `subprocess` with a string.
4. Policy tests: each refused policy shape in the Policy section fails to load, and a failed
   load refuses every command.
5. The helper refuses every case of criterion 1 on its own, tested by calling it directly.
6. The audit line has the fields above, never the output, and the command passes through
   `redact.py` (a command with `token=abc123` is logged masked).
7. `hosts.py` tests: the built `ssh` argument list has `BatchMode=yes`, `StrictHostKeyChecking=yes`
   and `IdentitiesOnly=yes`, and a refused string is refused before `ssh` starts (a fake `ssh`
   records whether it ran).
8. The `--self-test` on production passes after the install, and its refusal list includes
   criterion 1's characters.
9. With the Portainer and GitLab tokens, a write call is refused by the service.

## Related Docs

- [Bug report 077](../../bug-reports/077-unattended-claude-runs-skip-permissions.md): why every
  route to production is a wrapper that does one thing, and why a secret must not reach the
  agent's environment.
- `tools/muma_mcp/__init__.py`, `guard.py` and `redact.py`: the existing read-only server, its
  SQL guard ("the real boundary is the database account") and its log masking.
- Issue #176: the decision of 2026-11-12.
