# Public Edition: Technical Design

> Implements [functional.md](functional.md). Tracked by issue #189 (plan "prompt v5", steps 0 to 13).
> This design is step 3. Steps 4 to 12 start after Teun approves it.

Personal values are named by class, as in the functional design. The exact patterns live in
`scripts/ci/public-patterns.txt` (created in step 10), not in this document.

## Data Model

One new setting, no table change.

| Key | Where | Default | Notes |
|---|---|---|---|
| `public_source_url` | `ConfigStore` schema, group "About" | Placeholder GitHub URL, filled in later | Read by `GET /api/about`; shown on the web and app About screens |
| `project_url` | `ConfigStore` schema, group "About" | Same placeholder | Goes into outgoing User-Agent strings |

Both are plain, non-secret fields. Environment names: `PUBLIC_SOURCE_URL`, `PROJECT_URL`. The
precedence rules of `config_store.py` apply (API value, then environment, then default).

No migration. The `schema_migrations` and expand-only rules are not touched.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/about` | none, no auth (the AGPL offer must be reachable without login) | `{ "version": str, "source_url": str }` | none; `source_url` is the placeholder until configured |

No breaking change. The existing API is untouched. All consumers of the About screen (web frontend,
muma-mobile) change in the same MR (rule 7).

### Configuration by component

Each row names the code to change. Line numbers are from the step 0 inventory on 2026-10-27.

| Component | Change |
|---|---|
| `services/common/store_lookup.py:49`, `services/music_manager/artist_image_fetcher/safe_fetch.py:39`, `providers/musicbrainz.py:94`, `services/common/Helpers/ArtistEvidence.py:26`, `services/music_manager/popular_tracks/clients.py:41` | One helper, `services/common/user_agent.py`: `build_user_agent(product, version)` returns `"<product>/<version> (+<project_url>)"`. The five constants call it. A unit test fails when a module under `services/` builds a User-Agent without it |
| `services/music_manager/routers/management.py:343` | `PHPMYADMIN_URL` default becomes empty; the UI hides the link when empty |
| `scripts/*.py`, `tools/*.py` (`cleanup_redundant_indices.py`, `quick_inspect.py`, `check_db_structure.py`, `db_backup_json.py`, `db_url.py`, `inspect_table_content.py`, `library_stats.py`, `import_lms_users.py`, `backfill_release_dates.py`, `seed_scene_group_date_formats.py`, `restructure_music_folders.py`) | Read `DB_HOST`, `DB_USER`, `DB_PASS`, `REMOTE_HOST` from the environment through one helper, `tools/env_required.py`; exit 2 and name the variable when it is missing. Issue #188 is step 1 of the plan and lands before this design is implemented |
| `scripts/ci/prod-ssh-setup.sh`, `scripts/ci/prune-prod-images.sh`, `scripts/deploy.sh`, `scripts/ci-deploy.sh`, `scripts/ci/renovate.sh`, `scripts/dev.sh`, `publish.sh`, `.env.example`, `docker/Dockerfile.music-manager`, `scripts/ci/disk_janitor_plan.py`, `scripts/ci/prod_image_prune_plan.py` | Host, project path, registry user from variables (`PROD_REMOTE_HOST`, `CI_PROJECT_PATH`, `DOCKER_USER`). `DOCKER_USER` default `muma`. Image prefixes in the janitor come from `DOCKER_USER` |
| `services/frontend` | Placeholder `demo-user` in `ScrobbleTab.svelte`; test fixtures use `example.org`. UI text "Spotify UI" becomes "Web player" in `nl.json`, `en.json` and the other locale files, and in `docs/` |
| `services/muma-mobile/app/build.gradle` | `buildConfigField "String", "SERVER_URL"` and `"GOOGLE_CLIENT_ID"` from `project.findProperty('muma.serverUrl')` and `'muma.googleClientId'`; `APK_HOST_URL` default empty. `StaticServers.SERVER_URL` returns `BuildConfig.SERVER_URL` |
| `RESTMusicService.kt:86`, `SubsonicAPIClient.kt:205` | Replace `contains(<owner domain>)` by a lookup of the MuMa API base from the server's `getOpenSubsonicExtensions` answer, with the current heuristic kept only for URLs that carry `/muma` already. `CapacitorContractTest` and `LogRedactionTest` move to `example.org` |
| `.gitlab-ci.yml` | Two comments (lines 204 and 205) lose the runner host names. Deploy jobs already read `$PROD_URL`. The rest is checked by `public:check` |
| `CODEOWNERS` | Owner user name replaced by a placeholder |
| `services/music-management-server` | `FUNDING.yml`, `Dockerfile-release` maintainer label and `scripts/remote-build.sh` (a LAN address) are upstream files with local edits. Reset `FUNDING.yml` to the repository's own placeholder (step 10), set the label to the project name, delete `remote-build.sh` (moved to `muma-ops`) |

Android pipeline: CI variables `MUMA_SERVER_URL` and `MUMA_GOOGLE_CLIENT_ID` are passed as
`-Pmuma.serverUrl=...` and `-Pmuma.googleClientId=...` in the release and smoke jobs. A build without
them gets the neutral defaults, and `mobile:smoke` for the owner's APK runs with them set, so the owner's
APK is byte-for-byte equal in behavior. A first-run "enter your server" screen is a separate issue.

### Source workers as profiles

In `docker/docker-compose.full.yml` the services `soundcloud-fetcher`, the YouTube fetcher, the
Telegram fetcher and the importer get `profiles: ["soundcloud"]`, `["youtube"]`, `["telegram"]`,
`["importer"]`. The owner's deploy sets `COMPOSE_PROFILES=soundcloud,youtube,telegram,importer` in
the production environment file, which `scripts/deploy.sh` already sources. Production runs
docker-compose v1 (memory: `prod_runs_docker_compose_v1`), which supports `--profile` and
`COMPOSE_PROFILES` from 1.28. The step checks the version on the host and checks that every worker
is `Up` after the deploy. `docker/compose.test.yml` is unchanged.

### The `public:check` job

`scripts/ci/public-check.sh`, run by the job `public:check` in the `quality` stage, a required MR job:

1. `gitleaks dir` over the tree with `.gitleaks.toml`. `.gitleaksignore` is emptied in step 12.
2. `git grep -n -I -E -f scripts/ci/public-patterns.txt` over tracked files. The pattern file holds one
   regular expression per class: the owner's domain, the owner's GitLab and Docker user name, private LAN addresses,
   the brand word followed by a dot, the OAuth project number, the password manager name, and a
   third person's name found by the privacy step.
3. Allowed exceptions are written into the patterns with lookarounds: the Android package id and the
   GitHub contact address. `scripts/ci/public-patterns.txt` is the only list; there is no allowlist file.
4. Two paths are excluded from the grep: the pattern file itself, and `migrate_*.sql`. A deploy re-runs a
   migration whose sha256 changed, so a migration is never edited, even to remove a name. A unit test in
   `tests/ci/` feeds the script a temporary repository with one fixture per forbidden and per allowed form,
   so a typo cannot disable a check.
5. Exit 1 prints file, line and pattern class, never the matched value when the class is a credential.

The RFC 5737 and RFC 1918 addresses in tests (`203.0.113.9`, `198.51.100.7`, `10.0.0.0/8`,
a private-block CIDR written in a trusted-proxy default) are legitimate. The LAN pattern therefore matches any
host address and skips only that CIDR.

### Moving files to the private ops repository

The repository is private, created in step 8. Layout:

```
muma-ops/
  claude/            -> becomes .claude/ in a checkout (skills, settings)
  ai/, junie/        -> .ai/, .junie/
  prod/              -> scripts/prod/ (including person/)
  ops/               -> nightly-prod-check, crash-triage, ssh/known_hosts, vw.sh
  docs/              -> release-management.md, deployment-production.md, homelab sections of AGENTS.md
  install.sh         -> links the above into a checkout
```

`.claude/`, `.ai/`, `.junie/`, `scripts/prod/`, `scripts/ops` and `.production` are added to `.gitignore`
of the public repository, so a linked checkout never shows them as changes.

How a session loads the material:

- `muma-ops/install.sh <checkout>` creates symlinks from the checkout into `muma-ops`. The
  worktree bootstrap skill (which moves to `muma-ops`) runs it for every new worktree.
- The user's global `~/.claude/` rule `open-work.md` stays global and does not move.
- The public `AGENTS.md` says: "Operations material is in a private repository. Without it, ignore
  references to `scripts/prod/` and the production runbooks." The private `AGENTS.private.md` in
  `muma-ops` carries the homelab sections, and `install.sh` links it as `AGENTS.local.md`, which the
  public `AGENTS.md` names as an optional include.
- A session on a machine without `muma-ops` still builds, tests and opens merge requests.

Scripts and CI jobs that call `scripts/prod/` today:

- CI jobs must not call it. The step lists every call site first (`git grep -n 'scripts/prod'`), and
  each is either deleted, moved with the script, or replaced by a CI-side script that stays public.
- The deploy scripts `scripts/deploy.sh` and `scripts/ci-deploy.sh` stay public: they read hosts from
  variables and are useful to a self-hoster with SSH access.

### Deploys

Variables set in GitLab CI/CD (masked or file type where they hold a secret), with no literal host
left in `.gitlab-ci.yml`:

| Variable | Used by |
|---|---|
| `PROD_REMOTE_HOST`, `PROD_REMOTE_USER`, `PROD_REMOTE_DIR` | `scripts/ci/prod-ssh-setup.sh`, `scripts/ci-deploy.sh` |
| `PROD_SSH_KNOWN_HOSTS` (file) | replaces `scripts/ssh/known_hosts` |
| `PROD_URL` | environment URL, smoke checks (already used) |
| `DOCKER_USER` | image names in build, push, prune |
| `COMPOSE_PROFILES` | the profile list for the owner's deploy |
| `MUMA_SERVER_URL`, `MUMA_GOOGLE_CLIENT_ID` | Android builds |
| `RENOVATE_ENDPOINT`, `RENOVATE_REPOSITORIES` | `scripts/ci/renovate.sh` (defaults removed) |

`release:check-secrets` gets the new variable names. `scripts/ci/check-required-secrets.sh` and
`docs/deployment.md` (public part) list them.

Check after the step: a release pipeline on a throwaway `release/*` branch deploys to production with
the variables only, and `/health` shows the version. The ordering traps in `muma-release` apply and the
skill moves to `muma-ops` together with the rest.

## The history rewrite (steps 11 and 12)

Tooling: `git filter-repo` on a fresh `git clone --mirror` in the scratchpad. Never in the working
checkout. Keep the files `filter-repo/commit-map` and `ref-map`.

### Measured starting point

9,341 commits and 495 tags (`git tag | wc -l`, 2026-10-27). The plan said 204 tags. The success check
is "the tag count is unchanged by the rewrite": count before in the mirror, count after in the
rewritten mirror. The commit count may change only by commits that become empty, and the dry run
reports that number. The `git rev-list --all` count on a shallow checkout is smaller; the mirror clone
is full.

### Paths removed (`--invert-paths`)

- `.env`, `.server-env.json`, in all of history.
- Emulator core dumps (#182).
- Everything that moves to `muma-ops`, at every historic path: `scripts/prod/`, `.claude/`, `.ai/`,
  `.junie/`, `scripts/ssh/known_hosts`, `scripts/nightly-prod-check/`, `scripts/crash-triage/`,
  `scripts/vw.sh`, `docs/release-management.md`, `services/music-management-server/scripts/remote-build.sh`.
- Everything deleted by the docs cleanup: `docs/superpowers`, `docs/branding/candidates/`,
  `docs/open-work.md`, `docs/branch-hygiene.md`, `docs/festival-lineup-open-names.md`,
  `docs/machine-learning.md`, `docs/ml-tutorial.md`, `docs/OVERVIEW.md`, `docs/system-data-flow.md`,
  `docs/architecture/responsibilities.md`.
- Old paths of renamed trees (`services/ultrasonic`, earlier names of `scripts/prod`): the dry run
  lists them with `git filter-repo --analyze` and the path list is extended from that report.

The list is generated into `filter-repo/paths.txt` by a script from the same source as the docs
cleanup, so the two cannot drift.

### Text replacement (`--replace-text` and `--replace-message`)

One file per mode, `filter-repo/replace-text.txt` and `replace-message.txt`, kept in `muma-ops`
(they contain the real values). Mapping, per class:

| Class | Replaced by |
|---|---|
| Owner's domain, as `host.domain` | `example.org` with the same subdomain, for example `host.example.org` |
| Owner's GitLab host | `gitlab.example.org` |
| Owner's push host | `ntfy.example.org` |
| the owner's GitLab path (path, merge messages) | `muma/music-management` |
| Owner's Docker and GitLab user name as a standalone word | `muma` |
| a private LAN host address | `192.0.2.<n>` (RFC 5737, keeps scripts readable) |
| Google OAuth client id | `<google-client-id>.apps.googleusercontent.com` placeholder |
| Every credential in `.gitleaksignore` and the prod DB password | `<redacted>` |
| The brand word followed by a dot in a host name | `player.` |
| Password manager name | `password manager` |
| A third person's address (bug report 020) | `user@example.org` |

Regular expressions go first and literals second, longest match first. The Android package
The Android package id and the GitHub contact address are protected with a first rule that maps them to
themselves with a sentinel, and a last rule that restores the sentinel.

`--replace-message` uses the same mapping for messages. It adds the GitLab references below.

### GitLab references

About 1,080 messages contain `#123` or `!456`. On GitHub they would link to unrelated issues. In
commits made in this repository they become `GL-123` and `GL-MR-456`. Upstream commits keep theirs,
because the numbers belong to their own trackers.

How to tell them apart. `origin/develop` is a shallow checkout, so the investigation used the author
data in `git log --all`. Upstream authors are the LMS and Ultrasonic contributors: the LMS
maintainer's identities author about 2,300 commits, and 568 commits have the committer `GitHub
<noreply@github.com>`. The upstream history is reachable through the old release tags
(`1.5.2`, `1.6`, and the `muma-mobile-v*` series), and was merged into this repository.

Rule used in `--commit-callback`: a commit is local when its author e-mail is in the owner set. That
set is the owner's identities (after the mailmap), the bot `ci-release-tagging`, `Renovate Bot` and the
two `Claude (nightly)` names. Everything else is upstream and its message is returned unchanged. The
callback rewrites a reference only inside a local commit. Two checks keep this honest:

1. The set must cover every commit that touches only files outside `services/music-management-server`
   and `services/muma-mobile` before the monorepo import. The dry run counts the commits where the author
   is not in the set and the message has `#N`, and prints 20 at random for reading.
2. Merge commits by the owner that merge upstream are local. Their messages usually name a branch and no
   number, and the count of such messages is reported.

An alternative, `git rev-list` of commits reachable only from the upstream merge parents, is kept as a
cross-check: the two sets must agree on all but a reported handful of commits.

### Identities (`--mailmap`)

`filter-repo/mailmap` maps to the owner's name with the GitHub contact address:

- the three identities of the plan (two gmail addresses under the owner's name and user name),
- the owner's display-name variants with the personal address,
- the two `Claude (nightly)` names with the personal address (name kept, address mapped),
- the work address (296 commits), if Teun agrees (open question 1),
- the committer `root@lms.<LAN address>`.

Upstream authors and committers, `GitHub <noreply@github.com>`, `Hosted Weblate` and the other
contributors are not in the mailmap and keep their addresses. The mailmap file lives in `muma-ops`,
because it holds the old addresses.

`ci-release-tagging` has a GitLab no-reply address that contains the owner's host. It is mapped to
`ci-release-tagging <ci@example.org>`.

### Checks on the rewritten mirror

1. `gitleaks git` over all refs finds nothing.
2. `git log --all -p` and `git log --all --format=%B` have zero hits for every class in the pattern file,
   apart from the two allowed exceptions.
3. `git count-objects -vH` shows less than 500 MB.
4. `git tag | wc -l` equals the count before the rewrite.
5. Upstream commits: for 200 random upstream commits the author, committer and message are byte-equal
   before and after (the tree changes only through the path removals).
6. A checkout of `develop` passes `scripts/test/music-management-unit.sh` and `scripts/lint.sh`, and
   `docker build` of the three images works.
7. `ref-map` and `commit-map` are saved to `muma-ops` and attached to #189.

The dry-run numbers are posted on #189. Step 12 starts only after Teun's explicit go.

### Apply (step 12)

In this order:

1. Backup: `git clone --mirror` of the old repository and a GitLab project export, stored outside the
   repository and outside the scratchpad.
2. Unprotect branches and tags. Force-push all branches and all tags from the rewritten mirror with
   `git push --force --all -o ci.skip` and `git push --force --tags -o ci.skip`. `ci.skip` stops release
   and deploy pipelines from running on rewritten tags. Protect them again.
3. GitLab repository cleanup (Settings > Repository > Maintenance > Cleanup) with the `commit-map`, so
   objects behind merge-request refs are purged. Merge request diffs and discussions keep the old text
   until cleanup finishes; the open merge requests are retargeted or closed.
4. `.git-blame-ignore-revs`: each SHA is looked up in `commit-map` and replaced. A SHA that is not in
   the map is dropped and reported.
5. Empty `.gitleaksignore` of the entries for rotated secrets. Update its header and `AGENTS.md`: the
   history is clean.
6. Re-clone the workstation checkout, recreate worktrees, run `muma-ops/install.sh`.

Check: a fresh clone passes `gitleaks git` and the pattern grep, the next MR pipeline is green, and a
deploy of the next release reaches production.

Rewriting history does not un-leak a secret. Step 2 of the plan (rotation) comes first, and no
credential is accepted as "fixed" by the rewrite.

## Cross-App Impact

| App | Change |
|---|---|
| music-manager | `GET /api/about`, two config fields, the user-agent helper, the neutral defaults above |
| frontend | About screen "Source code" link, neutral fixtures, "Web player" naming, locale files |
| muma-mobile | BuildConfig fields, About screen link, host checks, tests, CI variables. Changed in the same MR as `GET /api/about` (rule 7) |
| LMS (`music-management-server`) | Label, `remote-build.sh`, comments; the web player naming in comments. No API change |
| CI | `public:check`, compose profiles in deploy, variable names, no literal hosts |
| Docs and agent material | Moves and deletions listed above; `AGENTS.md` shortened |

Each implementation step is its own MR to `develop` with tests, a changelog fragment, updated docs and
`Refs #189`, in the order of the plan. This design MR adds no fragment: it changes no behavior, so it
carries the `no-changelog` label.

## Technical Acceptance Criteria

1. `tests/ci/` has a test that fails on a literal password in a `pymysql.connect` call, and on a
   literal host default in `scripts/` and `tools/`.
2. `build_user_agent` has a unit test, and a second test fails on a hard-coded User-Agent under `services/`.
3. `GET /api/about` returns the configured URLs without a session. It reads no table, so a unit test
   covers it.
4. `muma-mobile` unit tests pass with the neutral defaults and with both Gradle properties set;
   `mobile:smoke` passes for the owner's build.
5. `docker compose -f docker/docker-compose.full.yml config --services` lists no source worker, and
   with `COMPOSE_PROFILES` set to all four it lists them. A deploy dry run on production shows every
   worker `Up`.
6. `public:check` fails on a branch that adds a LAN host address, an owner host name or a fake secret,
   and passes on `develop`. Its pattern fixture test passes.
7. The tree has no `git grep` hit for any pattern class outside the allowlist.
8. The rewritten mirror passes the seven checks above.
9. After step 12, `git rev-list --all --count` equals the dry-run count and `git tag | wc -l` equals the
   count before the rewrite.

## Related Docs

- Issues #189 (plan) and #188 (hard-coded database password).
- [docs/designs/README.md](../README.md), [AGENTS.md](../../../AGENTS.md).
- [docs/testing-inventory.md](../../testing-inventory.md), [changelog.d/README.md](../../../changelog.d/README.md).
