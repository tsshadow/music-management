# Unattended Claude runs on the runner host started with permissions switched off

# status: fixed

The code is fixed. It reaches the runner only when the root-owned copy in
`/opt/crash-triage/bin` is installed. That is a manual step, listed in `docs/open-work.md`,
with a guided script at `/tmp/muma-person/install-nightly-allowlist.sh`.

# reported problem

Audit finding B13. Three jobs on the runner host (`development`, 192.0.2.40) start
`claude -p` without anyone watching. All three used `--dangerously-skip-permissions`:

- **Crash triage.** `scripts/crash-triage/crash_triage_listener.py` runs for each uploaded
  Android crash report. The report (the stacktrace and the last 200 log lines) is text
  that any app user can write.
- **Nightly prod check.** `scripts/nightly-prod-check/run.sh` runs on a report built from
  production events and container logs. Anyone who can make production log a line can write
  part of that report, for example with a track title, an upload name or a request path. On
  develop this job had already moved to `--permission-mode dontAsk` with an allowlist
  (commit eb0522258). The runner clone ran that version on the night of 2026-09-25.
- **Approved-MR watcher.** `scripts/crash-triage/check_approved_mrs.sh` runs the
  `muma-release` skill after it merges an approved auto-fix MR. Its input is develop. Develop
  holds MRs that the two jobs above wrote from outside text. Teun approves them, but outsiders
  chose the text they started from.

With permissions off, a prompt injected into any of those inputs could do anything the
`triage` user can do. It could run any command. It could read the system API key and the
GitLab token from `crash-triage.env` or the process environment. It could POST, PATCH or
DELETE against production with the system key. It could push to any branch, merge and
release. It could also edit the scripts that set its own permissions, because the units ran
them straight from the clone that `triage` owns.

# Possible reason

"The host exists for this job alone", as `scripts/crash-triage/README.md` put it, was the
rationale. The skill prose and the MR pipeline were meant to be the guardrails. But prose is
exactly what a prompt injection overrides. And the pipeline only gates code that gets merged.
It does nothing about a command the run executes on the host.

The nightly job's first allowlist still had four gaps that an injected instruction could use:

- `python3 -m pytest`, `./scripts/lint.sh` and `./scripts/test/*` run code from the worktree
  the run writes into. A `conftest.py` is a shell with the system key in its environment.
- `git fetch *` allowed `--upload-pack=<cmd>`, and `git log/diff *` allowed `--output=<file>`
  (a write anywhere `triage` can write, including `~/.bashrc`).
- `sort *` and `uniq *` write files (`sort -o`, `uniq in out`).
- The project and user settings files still applied, so a `.claude/settings.json` could widen
  the list.

## What each user can reach on the runner host (measured 2026-09-25, read-only)

| User | Groups | Runs | Can write | Can read (beyond world-readable) |
|---|---|---|---|---|
| `triage` (uid 996) | `triage` only; no `docker`, no sudo (sudo is not installed) | the listener, the MR watcher, the nightly check; all three start Claude | its home `/opt/crash-triage/` (755, owned by `triage`): the clone `music-management/`, `state/` (ledgers, spool, logs, worktrees), `~/.claude/`, `~/.claude.json` (Claude OAuth token, 0600), `~/.config/` (glab); plus `/tmp`, `/var/tmp` | `crash-triage.env` (root:triage 0640: `MUMA_SYSTEM_API_KEY`, `GITLAB_TOKEN`, `NTFY_URL`); it can list `/home/gitlab-runner/builds` (755). It cannot read `/etc/gitlab-runner/config.toml` (root 0600) or `/opt/daily-briefing/` (750). |
| `gitlab-runner` (uid 999) | `gitlab-runner`, **`docker`** (root-equivalent) | CI jobs of the shell executor | `/home/gitlab-runner/`, and anything via Docker | Everything, via Docker. It does not start Claude: `.gitlab-ci.yml` has no `claude` call. |
| `briefing` (uid 995) | `briefing` only | `daily-briefing.service` (homelab repo, not this one) | `/opt/daily-briefing/` (750) | `daily-briefing.env` (root:briefing 0640). Its Claude run already uses `--tools ""`, so it has no tools at all. It needs no change and is outside this repository. |

So Claude with permissions off meant the whole `triage` column. `triage` has no Docker and no
root, which limited the damage to the host. But that column contains the production system key
and a GitLab token with push rights.

# solution

Every run now starts from one shared set of flags, built by
`scripts/crash-triage/claude-permissions.sh <nightly|triage|release>`:

- `--restricted`. Project, user and local settings files are ignored. The file tools, and the
  path arguments of read commands (`cat`, `grep`, `head`, even when a rule allows them), are
  confined to the working directories. Bypass mode is refused. Writes to git and settings files
  need a person.
- `--permission-mode dontAsk`. Anything not allowed is denied, never asked.
- `--strict-mcp-config`, and `--tools Read Grep Glob Bash Edit Write TodoWrite`. There are no web
  tools, no subagents and no Skill tool.
- `--add-dir <state>`. The working directories are the clone and `state/`. `$HOME` is not one,
  so `crash-triage.env` and `~/.claude.json` are out of reach.
- `safe.bareRepository=explicit` for every git the run starts, set through `GIT_CONFIG_*` in the
  environment. The Edit rules also deny `.git` and `.claude/settings*.json` inside the
  worktrees, so a run cannot give git a config that executes something (`core.fsmonitor`,
  `core.sshCommand`).
- A per-job allow/deny list. A deny wins over an allow. There is no curl and no raw `glab api`.
  Production and ntfy are reached only through wrappers that each do one thing:
  - `nightly-prod-check/prod-get.sh`: GET `/api/...` or `/health` (unchanged).
  - `crash-triage/crash-status.sh <id> <status>`: the one PATCH the triage run makes.
  - `crash-triage/ntfy-send.sh`: one message to the configured topic. A click link must point
    at GitLab.
  - `crash-triage/gitlab-get.sh`: a GitLab GET for this project. A download may only land in a
    worktree, never in its `.git`.
  - `crash-triage/merge-release-mr.sh <iid>`: release run only. It merges an open
    `release/x.y.z` or `hotfix/x.y.z` MR into master, pinned to its head. It does so only when
    the MR pipeline and the branch pipeline are both green, because merging earlier cancels
    `muma:deploy`.

What each job may do:

| | nightly | triage | release |
|---|---|---|---|
| edit | its worktrees, the result file | its worktrees, `ledger.json` | the eight stabilize files in a `release-*` worktree |
| push | `nightly-fix/*` | `crash-fix/*` | `release/*` |
| GitLab | `mr create/view/list` | `mr create/view/list`, `gitlab-get.sh` | `mr create/view/list`, `ci retry`, `gitlab-get.sh`, `merge-release-mr.sh` |
| production | `prod-get.sh` | `prod-get.sh`, `crash-status.sh` | `prod-get.sh` (for `/health`) |
| ntfy | no (run.sh sends it) | `ntfy-send.sh` | `ntfy-send.sh` |
| run code | none | `retrace` if installed | `python3 scripts/release/assemble_changelog.py` (a file this run cannot edit) |

No job runs tests or lint locally any more. That is the one capability that shrank: last
night's nightly run ran `tests/ci/` before opening !959. A test run executes code the run just
wrote, and it inherits the system key. The MR pipeline runs the same checks minutes later, and
it was already the gate. The skills now say to state in the MR that the checks were left to the
pipeline.

Other changes:

- `--restricted` does not load project skills. Each prompt therefore tells the run to Read
  `.claude/skills/<name>/SKILL.md`, and names the wrappers by absolute path. The run cannot
  expand a `$VARIABLE` in a command, which was tested with 2.1.280; the runner has 2.1.251.
- The crash triage now works in a worktree under `state/worktrees/` instead of on a branch in
  the clone. The release run cuts `release/x.y.z` as a worktree too. The watcher's release run
  gets a timeout (`RELEASE_TIMEOUT`, 3 h), a log file under `state/logs/`, and an ntfy message
  when it fails.
- The units run a root-owned copy at `/opt/crash-triage/bin/{crash-triage,nightly-prod-check}/`
  instead of the clone. The nightly `git reset --hard origin/develop` no longer replaces the
  running code, and a run can no longer edit the file that sets its own permissions. The
  deployment steps are in `scripts/crash-triage/README.md`, "Where the units run from".
- Tests:
  - `tests/ci/test_claude_run_permissions.py` pins the triage and release lists and every
    wrapper's refusals, runs `merge-release-mr.sh` against a fake `glab`, and checks that the
    listener, the watcher and the units use the new flags and the copy.
  - `tests/ci/test_nightly_prod_check_permissions.py` now reads the nightly list from the library.
  - `tests/ci/test_no_skip_permissions.py` fails when the skip flag, or the bypass permission
    mode, appears in any tracked file outside `docs/` and the changelogs.

The flag behaviour was checked with a real `claude -p` run (2.1.280, throwaway directory),
under `--restricted` and dontAsk:

- A read outside the working directories was refused, even for a command a rule allows.
- A write outside the Edit rules was refused, and so was a `.git/config` write inside them.
- `$VAR` expansion was refused.
- Project skills were not loaded.
- `git worktree add`, `cd`, `add` and `commit` inside an added directory worked.

**Not covered.** `triage` can still read its secrets through a path this list did not foresee.
The list narrows what an injected instruction can do directly. It does not replace privilege
separation. That would mean wrappers that run as a second user holding the key, so the Claude
process never has it in its environment. `docs/open-work.md` records that as the next step if
the threat grows.
