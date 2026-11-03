# Public Edition: Functional Design

> Tracked by issue #189 (and #188). Technical contract: [technical.md](technical.md). This design needs
> Teun's approval before any implementation step starts (AGENTS.md rule 4).
>
> Wording note: this document names personal values by class ("the owner's domain", "the owner's
> GitLab user name") and never prints them, so the document passes the `public:check` job it describes.

## Overview

The repository is to be mirrored to GitHub as open source, with its full history. Today the tree and
the history contain personal values: the owner's domain and LAN addresses, his GitLab and Docker user
name, a Google OAuth client id, e-mail addresses, production runbooks, agent material and some
credentials.

The public edition has one repository and one history. After it, `master` and `develop` contain no
personal value. Every value that differs per installation is configuration with a neutral default.
Operations material (production scripts, runbooks, agent skills) lives in a new private repository,
the private ops repository. A CI job, `public:check`, fails a merge request when a personal value comes back.
The history is rewritten once, so no commit, tag or commit message ever contained one.

Out of scope: renaming the Android package id, creating the GitHub repository,
pushing or mirroring to GitHub, the module split of the downloaders (#190).

The numbers below were measured on `origin/develop` and in `git log --all` on 2026-10-27. The
inventory files are in the scratchpad of the session that did step 0.

| Measure | Value |
|---|---|
| Commits in `git rev-list --all` | 9,341 |
| Tags | 495 (the plan said 204; 495 is the measured number) |
| Tree hits of the owner's domain, excluding the Android package and the allowed contact address | 73 files, 457 lines |
| Tree hits of the owner's user name | 76 files, 190 lines |
| Tree hits of a private LAN address | 85 files, 207 lines |
| Tree hits of the media-player brand name | 53 files, 126 lines |
| Commit messages with the owner's user name | 971 |
| Commit messages with a `#N` or `!N` GitLab reference | about 1,080 |

## User Stories

- As a self-hoster, I want to clone the repository and start it with my own domain, my own Google
  OAuth client and my own server URL, so that nothing points at someone else's server.
- As a self-hoster, I want the downloaders and the importer to be off until I turn them on, so that I
  choose which sources run on my machine.
- As a user of the web UI or the app, I want a "Source code" link on the About screen, so that I can get
  the source of the server I use (AGPL-3.0 section 13).
- As the maintainer, I want production scripts, runbooks and agent skills in a private repository, so
  that the public repository holds only what every installation needs.
- As the maintainer, I want my own deploys and my own APK builds to behave exactly as before.
- As a reviewer, I want CI to fail a merge request that adds a host, an address, a credential or a
  personal name, so that the public edition stays clean without a manual audit.

## Functional Flows

### What becomes configurable

Each row is a value that is a code default today (the "code default" hits of the inventory). The neutral
default is what a fresh clone gets. The maintainer's installation sets the old value through environment
or CI/CD variables.

| Component | Today | Neutral default | Set by |
|---|---|---|---|
| Backend: user agent of the importer's store lookup, the artist image fetcher, the popular tracks client, the artist evidence client and the MusicBrainz provider | Contains the owner's GitLab project URL | `muma/<version> (+<project URL>)` with `<project URL>` from the setting `project_url`, default the future GitHub URL placeholder | `PROJECT_URL` |
| Backend: phpMyAdmin link in the management router | Owner's domain on port 8002 | Empty, the link is hidden | `PHPMYADMIN_URL` |
| Backend: LMS endpoint comment and defaults that name a LAN address | Prose only | Reworded, no address | none |
| Scripts and tools (`scripts/*.py`, `tools/*.py`, `scripts/import_lms_users.py`, `scripts/ci/prod-ssh-setup.sh`, crash-triage env example) | Default host is the production LAN address; `quick_inspect.py` and `cleanup_redundant_indices.py` hold it literally, the second with a password | No default. The script exits with a message naming the missing variable (`DB_HOST`, `DB_USER`, `DB_PASS`, `REMOTE_HOST`) | Environment, CI/CD variables |
| Docker user | the owner's user name in `.env.example`, `Dockerfile.music-manager`, `scripts/dev.sh` | `muma` | `DOCKER_USER` |
| Frontend fixtures and placeholders | The owner's user name as a placeholder in the scrobble tab; the owner's domain in tests | `demo-user`, `example.org` | none |
| Frontend and docs: the name "Spotify UI" | Names the web player in UI text, code comments and docs | "Web player". The Subsonic endpoint file that implements the Spotify-style paging keeps its name in the C++ server, because it is an API shape, not branding. Calls to Spotify's own API (artist images) stay | none |
| Android: `StaticServers.SERVER_URL` | The owner's server URL | `BuildConfig.SERVER_URL`, default `https://example.org` | Gradle property `muma.serverUrl` |
| Android: Google OAuth client id | The owner's client id | `BuildConfig.GOOGLE_CLIENT_ID`, default empty, Google sign-in hidden when empty | Gradle property `muma.googleClientId` |
| Android: APK host URL | The owner's APK host | `BuildConfig.APK_HOST_URL`, default empty, update check off | `APK_HOSTER_URL` |
| Android: host checks in `RESTMusicService` and `SubsonicAPIClient` (`url.contains(<owner domain>)`) | Special-case the owner's hosts | Derived from the configured server URL: the MuMa API host is read from the server's capabilities, not guessed from a domain | none |
| AGPL source offer | Not present | Setting `public_source_url`, shown as "Source code" on the web About screen and the app About screen | Management > Configuration |
| Renovate, CODEOWNERS, `.gitlab-ci.yml` comments | Owner's user name and host names | CODEOWNERS uses a team alias placeholder. Comments name roles ("the workstation runner"), not hosts | none |

### What moves to the private ops repository

| Moves | Why |
|---|---|
| `scripts/prod/` (58 tracked files in `scripts/prod/`, `.claude/`, `.ai/` and `.junie/` together) | Operates the owner's production host |
| `.claude/` (skills for prod check, release, nightly check, crash triage, MR flow, worktree bootstrap) | Agent material that names hosts, tokens and the owner's workflow |
| `.ai/`, `.junie/` | Agent plans and requirements |
| `.production` handling (the file is already gitignored; the docs and scripts that read it) | Describes the production host |
| Homelab and production sections of `AGENTS.md` | The public `AGENTS.md` keeps repository layout, modules, testing and rules |
| `docs/release-management.md` and the production part of `docs/deployment.md` | Describe the owner's release and deploy path |
| `scripts/ssh/known_hosts` | Pinned host keys of the production host |
| `scripts/nightly-prod-check/`, `scripts/crash-triage/`, `scripts/vw.sh` | Run against production or the owner's password manager |
| `security/` entries that name the owner's paths stay; entries that print owner values are rewritten | Accepted-findings lists are public-safe once the paths are neutral |

A session still loads this material: the owner's workstation checks out `muma-ops` next to the
repository and links its `.claude/` into the checkout. See the technical design for the mechanism.

The public repository keeps working without `muma-ops`: every test script, the build, and CI.

### Deploys

The owner's deploy behaves as before. Hosts, paths and users come from CI/CD variables
(`PROD_REMOTE_HOST`, `PROD_URL` and the others listed in the technical design). `.gitlab-ci.yml` stays
in the repository, with no literal host or address. A self-hoster does not use it; the public
README says GitLab CI is not part of the public setup.

### Sources are opt-in

The downloader and importer stay in the repository. In `docker/docker-compose.full.yml` each source
worker (soundcloud, youtube, telegram, importer) gets a Compose profile. A plain `docker compose up`
starts no source worker. The owner's deploy passes every profile. The README describes the importer as
a tool for music you bought or got as a label promo, and the downloaders as tools that fetch what an
artist or label published on their own channel.

### Docs cleanup

| Action | Paths |
|---|---|
| Delete | `docs/superpowers` (89 agent plans), `docs/branding/candidates/`, `docs/open-work.md`, `docs/branch-hygiene.md`, `docs/festival-lineup-open-names.md` |
| Fold into `services/ml-analyzer/DEPRECATED.md`, then delete | `docs/machine-learning.md`, `docs/ml-tutorial.md` |
| Move to `muma-ops` | `docs/release-management.md`, production part of `docs/deployment.md` |
| Write | `docs/self-hosting.md` (compose, `.env`, profiles, migrations, backups) |
| Merge into one `docs/architecture.md`, written for people, every claim checked against the code | `docs/OVERVIEW.md`, `docs/architecture.md`, `docs/system-data-flow.md`, `docs/architecture/responsibilities.md` |
| Translate to English | `docs/security-checks.md`, `docs/designs/mobile-cover-art/` |
| Keep and scrub | `docs/bug-reports/` (532 files refer to them), `docs/designs/` |
| Remove third-party personal data | `docs/bug-reports/020-*` and any other file where the inventory finds a third person's address |

Dutch UI strings (`nl.json`, `brabants.json`, `sallands.json`, Android `values-nl*`) are translations,
not leaks, and stay.

### The `public:check` job

A required merge request job. It fails when gitleaks finds a secret in the tree, or when a pattern list
finds a personal value. Two exceptions are allowed: the Android package id and the GitHub contact address.

### The history rewrite

Done once, in two steps with a stop between them.

1. A dry run on a fresh mirror clone, with measured results reported on #189.
2. After Teun says go, the same rewrite is applied to GitLab, with backups.

After step 2 everyone re-clones. Open merge requests are retargeted or closed.

## Acceptance Criteria

1. A fresh clone, with no environment set, contains no host, LAN address, user name or credential of
   the owner in the tree.
2. A script that needs a host or a database password and does not get one stops with a message that
   names the missing variable.
3. The owner's production deploy reaches the same hosts as before, through CI/CD variables only, and
   `/health` shows the new version.
4. The owner's APK, built with `muma.serverUrl` and `muma.googleClientId`, behaves as before, and
   `mobile:smoke` passes.
5. `docker compose -f docker/docker-compose.full.yml up` starts no source worker, and the same command
   with every profile starts all four.
6. The About screens of the web UI and the app show a "Source code" link to `public_source_url`.
7. `public:check` fails on a test branch that adds a LAN address, and passes on `develop`.
8. A session on the owner's workstation can load the agent skills from `muma-ops`.
9. After the rewrite, `gitleaks git` over the whole history finds nothing, a grep over all patches and
   all commit messages finds none of the patterns, the repository is below 500 MB, and the tag count is
   the same as before the rewrite.
10. After the rewrite, upstream LMS and Ultrasonic commits keep their authors and messages.
11. Every credential that was ever committed is rotated before the rewrite (step 2 of the plan).

## Open Questions / Not Yet Decided

1. Decided 2026-10-29: the work address and every spelling of the personal identities map to
   the owner's name and the GitHub contact address; the commits are the owner's own work. Every
   mention of the employer is removed from the history and blocked by `public:check`.
2. Decided: the `root@lms.<LAN address>` committer maps to a neutral `root@lms.example.com`.
3. Which GitHub Actions workflow names and ghcr.io namespace should the public images use? The plan
   says ghcr.io; the namespace is needed for step 10.
4. `CODEOWNERS` names the owner's user name. Proposal: replace it with a placeholder the GitHub owner
   fills in. Is that what you want?
5. The neutral Docker user `muma` is a proposal. A different name only changes one default.
