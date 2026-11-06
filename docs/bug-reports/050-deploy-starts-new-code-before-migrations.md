# The Deploy Starts New Code Before Its Migrations, With No Backup And No Way Back

# status: fixed — backup, migrate, promote, then up; `db` and the one-shots left alone; `:latest` moves only inside muma:deploy; verify re-samples; CI tests on the images' Python

# reported problem
A read of the deploy path (on top of MR !919) found six defects that together meant a release could
reach production in the wrong order, with nothing to fall back on:

1. **New code started before its migrations, without a backup, without a rollback.**
   `scripts/deploy.sh` ran `up -d --force-recreate` first and applied the `migrate_*.sql` files
   afterwards, one ssh call each. For the length of the migration loop the new code ran against the
   old schema. No backup was taken (the step in `publish.sh` is commented out), and every image was
   pinned to `:latest` in `docker/docker-compose.yml` although CI pushes a `:${VERSION}` tag of each
   one that nothing used — rolling back meant rebuilding.
2. **Every deploy recreated every container, `db` included.** CI never sets `SERVICE_NAME`, and the
   full-stack branch used `--force-recreate`, so MariaDB was restarted by every release, and the
   one-shot `soundcloud-fetcher` and `genre-processor` were started again each time (a full
   SoundCloud fetch per release).
3. **`:latest` was pushed before the deploy gated anything.** `release:build-images` pushed
   `:latest` in the `release` stage. Watchtower on the production host pulls `:latest` of the
   downloader images whenever it changes, so it could start a release's worker code minutes before
   `muma:deploy` had migrated — and did so even when `muma:deploy` was skipped altogether (a red
   mobile job skips it; see release 0.19.0 in the operator's release runbook).
4. **Post-deploy verification could pass while services were broken.**
   `scripts/ci/post-deploy-verify.sh` sampled container state once, right after the migrations. A
   container that crashes twenty seconds after start and is brought back by
   `restart: unless-stopped` looks "running" in that sample. The production compose file defined no
   healthcheck for music-manager or any worker, and LMS was not probed at all.
5. **CI tested a different Python, with different dependencies, than production runs.**
   `backend:unit` and `backend:integration` ran the runner's own `python3` — 3.11 on the LXC —
   with no dependency install, while every image runs 3.14. `requirements.txt` pins
   `numpy~=2.5.2`, which needs 3.12 or newer, so CI could not have been using it. Running the suite
   on 3.14 from `requirements.txt` alone found three real gaps: `httpx2` (required by
   `fastapi.testclient`) was not in `requirements.txt` at all, `git` is needed by
   `tests/ci/test_release_version_check.py`, and the `numpy` stub in `services/tests/mock_base.py`
   broke every hypothesis test (`'numpy' is not a package`, then `isinstance() arg 2 must be a
   type`).
6. **Exposure and resource defaults.** MariaDB (`3306`) and phpMyAdmin (`8002`) were bound on every
   interface, the Firefox noVNC login defaulted to `admin`/`admin`, no service had log rotation
   (Docker's default json-file log grows without bound — and a full disk on this host has already
   looked like an unrelated 502), and no container had a memory limit.

# Possible reason
The deploy script grew from "pull and restart everything", which is fine for a stack with no schema.
Migrations were bolted on at the end once there was a database, and the order was never revisited
because every migration so far was additive, so the window was short and nothing visibly broke.
Pushing `:latest` from the build job predates Watchtower on the host; once Watchtower was pointed at
the downloader images, the build job became a second, ungated deploy path. `--force-recreate` was
added once to get past a stale container and stayed. The CI Python drift is the same one
`scripts/lib/python-tooling.sh` already fixed for the linters: the runner's system Python was the
path of least resistance, and a green job never said which interpreter it was green on.

# solution
- **Order (1).** `scripts/deploy.sh` now runs five steps: (a) ship the compose file, start `db` only
  if it is missing (`up -d --no-deps --no-recreate db`) and wait until `mariadb-admin ping`
  answers; (b) take a verified pre-deploy dump — through the nightly backup's own entry point
  (`tools/db_backup.py` via the `db-backup` service in `/opt/muma-backup`, with
  `BACKUP_LABEL=pre-deploy`), falling back to `mariadb-dump` through `docker exec` into
  `HOST_BACKUP_PATH`, held to the same size/gzip/trailer checks — and abort when neither yields a
  verified dump; (c) apply every migration while the previous release still runs; (d) run
  `DEPLOY_PRE_UP_HOOK`; (e) `pull` and `up -d --no-deps --remove-orphans` the services that
  changed. `tools/db_backup.py` learned `BACKUP_LABEL` (a labelled dump keeps its own rotation of
  three and never replaces `latest.json`).
- **Migrations before up are safe only when they are expand-only.** Every current `migrate_*.sql`
  is re-runnable, and the eight that contain a contract step (a `DROP`, `MODIFY`, `CHANGE`,
  `RENAME` or `DELETE`: v2, v3_genre_states, v5_events, v6_youtube_video, v13_channels_binary_collation,
  v13_curation_edits, v19_work_key_binary, v29_processed_mtime_double) have all long been applied to
  production and are guarded into no-ops on re-run. `tests/ci/test_migration_ordering.py` now fails
  any *new* migration with a contract step; that step belongs in the release after the code stops
  using the old shape. A newer file whose match is harmless to the running release is listed, with
  its reason, in `REVIEWED_SAFE` — v33_listened_at_no_on_update, which only drops the accidental
  `ON UPDATE` from `listened_at`.
- **Rollback (1).** Every image this repository builds is `${IMAGE_TAG:-latest}` in
  `docker/docker-compose.yml` (a single-level default, rendered correctly by docker-compose 1.29.2 —
  checked). `IMAGE_TAG=<previous> ./scripts/deploy.sh` rolls back; see `docs/self-hosting.md#roll-back`.
  CI deliberately does **not** pin `IMAGE_TAG=${VERSION}`: the running containers must stay on
  `:latest`, or `muma:refresh-downloader`'s weekly yt-dlp rebuild — which republishes `:latest` for
  Watchtower — would never reach them again.
- **Recreation (2).** No `--force-recreate`. `db` is excluded from the update step unless
  `DEPLOY_DB=1`, the one-shots unless `DEPLOY_ONESHOTS=1` (and both carry `restart: "no"`); the
  missing-image cleanup only touches the services being updated. Compose profiles would have been
  tidier but need docker-compose 1.28+, which is not documented for the host, so it is an explicit
  service list.
- **`:latest` (3).** `release:build-images` pushes `:${VERSION}` and `:rc` only (lms also its C++
  version). `muma:deploy` moves `:latest` (and `:stable` for lms) from `:${VERSION}` in
  `scripts/ci/promote-release-images.sh`, run as the pre-up hook — after the backup and the
  migrations, before anything is recreated — with a registry-side `docker buildx imagetools create`
  where buildx exists. A pipeline whose deploy never runs never moves `:latest`.
- **Verification (4).** `docker/docker-compose.yml` gives music-manager a healthcheck on `GET
  /health` (which answers 503 when the database or a loop is down) and every worker a light one
  (Python runs, MariaDB accepts a TCP connection). `post-deploy-verify.sh` waits for `/health`,
  probes LMS's `/rest/ping.view`, then re-samples every container after 60 s and fails on any
  `RestartCount` increase or `unhealthy` state.
- **CI Python (5).** `backend:unit` and `backend:integration` run pytest inside
  `docker/Dockerfile.python-ci` (python:3.14-slim, the images' base, plus git and openssh-client),
  with `requirements.txt` installed into the per-hash tooling cache of `scripts/lib/python-tooling.sh`.
  `backend:lint`/`typecheck`/`format` always use their tooling container in CI now, on either
  runner. `httpx2` is in `requirements.txt`; the numpy stub registers `numpy.random` and a real
  `ndarray` class. mypy checks as 3.14. ruff's `target-version` moved from `py311` to `py313`, not
  `py314`: with `py314` `ruff format` rewrites `except (A, B):` into PEP 758's `except A, B:`, a
  SyntaxError on the 3.13 the workstation runs the pre-commit hook and `tools/muma_mcp` with.
- **Exposure and resources (6).** MariaDB and phpMyAdmin bind to `127.0.0.1` unless
  `DB_BIND_ADDRESS` / `PHPMYADMIN_BIND_ADDRESS` say otherwise (the workstation's read-only MCP
  connects to `192.0.2.27:3306` directly, so production needs `DB_BIND_ADDRESS` set — or the MCP a
  tunnel — before the next `DEPLOY_DB=1`). The Firefox password has no default, and
  `release:check-secrets` requires `FIREFOX_PASSWORD` in `PROD_ENV_FILE`. Every service logs through
  json-file capped at 3 × 10 MB, and music-manager (4g) and the workers (2g, telegram 1g) have
  overridable `mem_limit`s — conservative guesses, as no sizing is documented.
- **Tests.** `tests/ci/test_deploy_script_hygiene.py` runs the real scripts against fake
  `ssh`/`docker`/`docker-compose`/`curl`: migrations after the dump and before `up`; a failed,
  truncated or undersized dump and a missing backup destination each abort before any migration;
  `db` and the one-shots untouched by default; the hook between migrations and `up`; `IMAGE_TAG`
  validated and passed through; the release build pushes no `:latest`/`:stable`; promotion moves
  them from the VERSION file's tag; the verify script fails on a restart-count increase, an
  unhealthy container, a silent LMS and a wrong version. `tests/ci/test_gitlab_ci_policy.py` pins the
  CI side.
