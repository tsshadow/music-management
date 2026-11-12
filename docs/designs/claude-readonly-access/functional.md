# Read-Only Agent Access: Functional Design

## Overview

An agent session can see production only through the tools of the `muma-prod` MCP server
(`tools/muma_mcp`): `/health`, the container list, container logs and read-only SQL. It cannot list
a folder under `/mnt/music`, read one setting of a container or check a disk. After the import queue
moved (#51), the owner had to paste `ls` and `printenv` output into the session by hand. The same
gap exists on every other host the agent works on: the dev VM, the CI runners, the NAS, the Proxmox
node, Portainer and GitLab.

This design gives the agent a read-only view of those seven hosts (issue #176, decided on
2026-11-12):

- Five hosts get an SSH account whose key can run one program only: `muma-ro`. That program reads
  the command the agent sent, checks it against a fixed list of read-only commands for that host,
  and runs it without a shell. Anything else is refused. The five are production, the dev VM, the
  CI runners, the NAS and the Proxmox node.
- Two hosts are reached through their own API with a read-only token instead: Portainer and GitLab.

The agent uses these through new tools in the same MCP server. It never installs or widens its own
access: a person installs every key, wrapper and token with a script that shows a dry run first.

The wrapper is built and proven on production first. The other hosts get a copy once the parser
tests pass and production has run it for a week.

## User Stories

- As the owner, I want the agent to list a folder or read one container setting on production
  itself, so that I stop pasting command output into the session.
- As the owner, I want every command the agent can run on a host to be on a list I can read, so
  that I know what "read-only" means per host.
- As the owner, I want a refused command to say why, so that I can tell a missing verb from an
  attempt that should never work.
- As the owner, I want a log of every command each host received from the agent, so that I can
  check afterwards what it looked at.
- As the owner, I want a secret never to come back in the output, so that a log line or an
  environment variable does not leak a password into a session transcript.
- As the owner, I want one key to be removable without touching the others, so that I can cut
  the agent off from one host at once.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| The agent lists `/mnt/music/EPs/__TODO` on production | It gets the listing. The host's log has one line: time, key name, the command, `allowed`, exit code. |
| The agent asks for `/mnt/music/../etc/shadow` | Refused: "path outside the allowed roots". Nothing runs. The log has a `denied` line with the reason. |
| The agent sends `ls /mnt/music; rm -rf /` | Refused: "shell character `;` not allowed". Nothing runs. |
| The agent asks for `docker exec music-manager sh` | Refused: "docker exec allows only printenv with a listed key". |
| The agent asks for `printenv DB_PASS` in a container | Refused: "key not on the list for this host". |
| The agent asks for a listed key, for example the import folder setting | It gets the one value. |
| The agent reads the last 500 log lines of a container | It gets them, with known secret shapes masked, as `prod_logs` does today. |
| The agent asks for 100,000 log lines | Refused: "tail above 2000". |
| A command runs longer than its time limit | It is stopped. The agent gets the output so far and "timed out after 30 s". |
| Someone tries an interactive login with the key | The connection closes with "no command". There is no shell. |
| The agent asks the NAS for the music dataset's snapshots | It gets the snapshot list. It cannot create or remove one. |
| The agent asks Proxmox for a container's resource limits | It gets the container config, without the description field. |
| The agent asks Portainer or GitLab for state | It gets the answer through the read-only token. A write call is refused by the service itself. |
| The owner removes one key line on one host | That host refuses the agent from then on. The other hosts are not affected. |

## Acceptance Criteria

1. On each of the five SSH hosts, the agent's key cannot open a shell, forward a port or run any
   command that is not on that host's list.
2. Every command on a host's list reads only: none of them can change a file, a container, a
   dataset or a setting.
3. A path argument outside the allowed roots is refused, also through `..` and through a symbolic
   link that points outside.
4. A command with a shell character outside a quoted path is refused.
5. No environment variable outside the per-host key list can be read.
6. Each host logs every request with time, key name, command, decision and reason. The log has
   no command output.
7. The Portainer and GitLab tokens are refused by the service for every write call.
8. The agent reaches all seven hosts through MCP tools, and has no other route to them.
9. Production has run the wrapper for a week before any other host gets it.

## Open Questions / Not Yet Decided

1. Path arguments with `&`, `(` or `'`: music folders hold names like `Artist & Artist (Live)`.
   Refuse them, allow them inside a quoted path argument only, or have the tool encode paths.
2. One SSH key for all five hosts, or one per host.
3. GitLab: is the read-only token only for the new MCP tools, or does it replace the token the
   agent uses for merge requests today?
4. Portainer: which read-only role the installed edition offers, and whether the existing
   `portainer` MCP tools that restart and redeploy stay available to the agent.
5. Proxmox: the API with an auditor-role token for the node and backup state, or `muma-ro` over
   SSH for everything.
6. The CI runner that is also the owner's workstation: does it get the wrapper, or does the agent
   already read it as the local user?
