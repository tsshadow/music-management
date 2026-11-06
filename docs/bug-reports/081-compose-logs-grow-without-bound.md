# Container logs grow without bound outside the main compose file, and the deploy trusts any host key

# status: fixed

# reported problem

Audit item B12 (September 2026). Docker's default logging driver is json-file **without** a size
cap, so a container that is never recreated keeps appending to one file under
`/var/lib/docker/containers/` until the disk is full. On the production host a full disk has
already looked like a 502: the healthcheck stayed green and nginx simply stopped logging. The root
filesystem of that host was 86% used when this was reported.

The rest of B12 was re-checked at the same time:

- MariaDB and phpMyAdmin published on every interface;
- the Firefox noVNC login defaulting to `admin`;
- no memory limits;
- every ssh call to production with `StrictHostKeyChecking=no`;
- the deploy's `.env` parser cutting a value at the first `#`;
- the post-deploy check unable to see an unhealthy worker, because workers had no healthcheck.

# Possible reason

Bug report [050](050-deploy-starts-new-code-before-migrations.md) already added an `x-logging`
anchor (json-file, `10m` x `3`) to every service in `docker/docker-compose.yml`, the file
`scripts/deploy.sh` deploys. None of the other compose files had one:

- the `lms` stack (`services/music-management-server/docker-compose.yml`) — deployed to production
  by `deploy-stack.sh`, and the chattiest of all: LMS and its nginx front log one line per HTTP
  request;
- `docker/docker-compose.backup.yml` — run by the backup timers on production;
- `docker/compose.test.yml` — the CI test stack;
- `docker/docker-compose.core.yml`, `.full.yml`, `.tools.yml`, `.workers.yml`, `.dev.yml` — local or
  legacy stacks.

Nothing enforced it either, so the next compose file or service would have started without it again.

Of the other B12 items, 050 had fixed the bindings, the Firefox default, the memory limits and the
worker healthchecks — but only in `docker/docker-compose.yml`. Bug report
[038](038-deploy-puts-every-prod-secret-on-the-command-line.md) had fixed the `.env` parser
(`scripts/lib/dotenv.sh`). The host key was still open everywhere. `scripts/ci/prod-ssh-setup.sh`
appended whatever `ssh-keyscan` returned to the shared runner's `known_hosts`, and then every script
connected with `StrictHostKeyChecking=no` anyway. That accepts any key at all. Anything answering on
the production address would receive the root key's signature, the production env file on stdin,
and the migrations.

# solution

**Log rotation everywhere.** Every service in every compose file now has a `logging:` block. The
`*default-logging` anchor is the same `10m` x `3` that 050 chose (at most 30 MB per container).
With the root filesystem at 86%, the smaller budget is the better default, and the event log, not
`docker logs`, is the long-term history. `lms` and `reverse-proxy` get `*request-logging`,
`20m` x `5` (at most 100 MB each). Both log every request, and LMS is the log most often read
after an incident, so under the default it would have had the shortest history of any container.

`tests/ci/test_compose_log_rotation.py` finds the compose files by glob (`docker/*compose*.yml`,
`services/*/docker-compose*.yml`), so a new file is covered without anyone remembering the test. It
requires every service to have json-file logging with `max-size` and `max-file`, within an upper
bound of 50 MB x 10. Before the change it failed for all eight files. It also requires every file
that uses `x-` fields to declare compose format 3.4 or newer, or no version.

Compose v1 compatibility was checked with
`docker run --rm -v "$PWD":/w -w /w docker/compose:1.29.2 -f <file> config`, the version production
runs. These all render: `docker-compose.yml`, `compose.test.yml`, `docker-compose.backup.yml`,
`docker-compose.core.yml`, `docker-compose.full.yml`, the `lms` stack, `docker-compose.yml` +
`docker-compose.tools.yml`, and `docker-compose.yml` + `docker-compose.workers.yml`. The output
shows the resolved `logging` blocks. The `lms` file has no `version:`, and docker-compose 1.27+
reads that as the Compose Specification, which allows `x-` fields. Two combinations failed before
this change as well, so the change did not cause them: `docker-compose.tools.yml` on its own (it
depends on `db`), and the `scripts/dev.sh` overlay stack (`docker-compose.dev.yml` adds a
`music-management-server` service that no other file defines). The image was removed afterwards.

**The settings only apply to containers created after the deploy.** Docker fixes a container's
log configuration when it creates the container. `deploy.sh` recreates only what changed, and the
logging change counts as a change, so the application containers and the `lms` stack pick it up
on the next deploy. `db` is only recreated on a `DEPLOY_DB=1` deploy, so its log keeps growing
until then. A container's existing log file is not trimmed: it keeps its size until the container
is recreated, and then it is deleted along with the old container. The one-shot jobs and backups
run as `run --rm` and get the setting on their next run. To see what a running container has:
`docker inspect -f '{{.HostConfig.LogConfig}}' <container>`.

**Pinned host key.** The production host's three public keys (ed25519, ecdsa, rsa) are in
`scripts/ssh/known_hosts`, with their fingerprints. They were captured with `ssh-keyscan` on
2026-09-25 and matched against the workstation's long-standing `known_hosts` entries for the same
address. `scripts/lib/ssh_host_keys.sh` provides `ssh_host_key_opts HOST`:

- a host listed in the pinned file gets `StrictHostKeyChecking=yes`, checked against that file only;
- any other host (a Portainer host in `deploy-stack.sh`, a developer's own target) gets
  `accept-new` against the user's own `known_hosts`. That learns a key once and refuses it if it
  changes later.

`deploy.sh`, `ci-deploy.sh` (ssh and scp), `deploy-stack.sh`, `prod-ssh-setup.sh`,
`post-deploy-verify.sh` and `verify-prod-version.sh` all use it. `prod-ssh-setup.sh` no longer
runs `ssh-keyscan`, and when its connection probe fails it now prints ssh's own error, because a
changed host key and a refused login otherwise look the same. `SSH_PINNED_KNOWN_HOSTS` overrides the
file, for the window between a host reinstall and the repository catching up. The procedure is in
the operator's runbook, "Production host key". `tests/ci/test_ssh_host_keys.py` guards all of this.

**The smaller B12 items, state after this change:**

- MariaDB/phpMyAdmin loopback (`DB_BIND_ADDRESS`, `PHPMYADMIN_BIND_ADDRESS`): done in 050 for
  production. Now also in `docker-compose.core.yml` and `.full.yml`, which still published `3306`
  and `8002` on every interface.
- `FIREFOX_PASSWORD` required: done in 050 (no default, `release:check-secrets` requires it). The
  `admin` default is now also gone from `.tools.yml` and `.full.yml`.
- Memory limits: music-manager and the four workers have them since 050. `db`, `phpmyadmin`,
  `firefox`, the one-shots and the `lms` stack have none. This is left open deliberately, because
  there is no measured basis for a ceiling on MariaDB or LMS; see the GitLab issues.
- `.env` parser truncating at `#`: fixed in 038 (`scripts/lib/dotenv.sh`, tested in
  `tests/ci/test_deploy_script_hygiene.py`).
- Worker healthchecks for the post-deploy check: done in 050 (`x-worker-healthcheck`, and
  `post-deploy-verify.sh` fails on `unhealthy`).
- `StrictHostKeyChecking=no`: fixed here for every script that talks to production.
  `publish.sh` and `services/muma-mobile/scripts/deploy.sh` still use it. They publish to the
  apk-hoster, which is a different host, and they are out of scope here.
