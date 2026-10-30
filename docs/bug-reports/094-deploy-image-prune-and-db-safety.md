# Production's disk filled with old images, and DEPLOY_DB=1 recreated the database before its backup

# status: fixed

# reported problem

On 2026-09-26 the root disk of the production host (192.0.2.27) was 95% full: 5.5 GB free of
99 GB. `docker system df` showed 377 images totalling 67 GB, 61 GB of it reclaimable. Five
release/hotfix deploys had landed on 2026-09-25 alone. `docker image prune -a -f --filter until=72h`,
run by hand, freed 49.8 GB (44% used afterwards). A full disk on this host has presented as an
unrelated 502 before, with every healthcheck still green.

A rehearsal-script review of `scripts/deploy.sh` in the same session found two more problems:

1. A `DEPLOY_DB=1` deploy pulled and recreated the `db` container in its first step, *before* the
   verified pre-deploy dump ran. Had the new MariaDB failed to start, the newest backup would have
   been the nightly one.
2. The next `DEPLOY_DB=1` deploy is a major upgrade, 12.3.3 -> 13.0: the compose file names
   `mariadb:13.0`, a floating tag, while the running container is still on 12.3.3. Nothing set
   `MARIADB_AUTO_UPGRADE`, so the image's entrypoint would have started 13.0 on 12.3 system tables
   without running `mariadb-upgrade`.

And `muma-ops docs/deployment-production.md` offered an ssh tunnel (`ssh -L 3306:127.0.0.1:3306`) as the alternative
to `DB_BIND_ADDRESS=203.0.113.10` for the workstation's read-only MCP. That cannot work: the MCP's
account is `muma-readonly@'192.0.2.%'`, and through the tunnel the database sees the connection
coming from the docker bridge gateway (172.22.0.1), so it refuses the login.

# Possible reason

- **Images:** the deploy pulls every image on every release (`docker compose pull`), and each pull
  moves `:latest` to a new image, leaving the previous one untagged but on disk. Nothing in the
  deploy, and nothing on the host, ever removed them. The runner has a janitor
  (`scripts/ci/disk-janitor.sh`); production had none.
- **Order:** bug report 050 put the backup before the migrations, but kept `DEPLOY_DB=1`'s
  recreate in the "prepare" step, which has to run first because the dump needs a running
  database. Starting a missing database and replacing a running one were the same step.
- **Upgrade:** MariaDB's image only runs `mariadb-upgrade` on an existing data directory when
  `MARIADB_AUTO_UPGRADE` is set. The floating tag meant the version moved without any change to
  the repository. A second trap sat in the readiness wait: `mariadb-admin ping` over the socket
  also answers from the entrypoint's temporary upgrade server (started with `--skip-networking` on
  the same socket), so the migrations could have started against a server about to be shut down.
- **Tunnel:** the account's host part is part of its identity in MariaDB; a tunnel changes the
  client address the server sees.

# solution

- **Prune after a verified deploy.** `scripts/ci/prune-prod-images.sh` runs at the end of
  `ci-deploy.sh`, after `post-deploy-verify.sh` has passed. It keeps every image a container uses
  (running or stopped), per repository the `PRUNE_KEEP_RELEASES` (default 3) most recently built
  unused images for an `IMAGE_TAG` rollback, and anything tagged `latest`/`stable`/`rc` (the nightly
  db-backup runs `muma-tools:latest` with `run --rm`). The rest goes through `docker rmi` without
  `-f`, which refuses an image a container uses. It logs every removal and the free space before and
  after. A failed prune is a warning; it never fails a deploy. The decision is a pure function
  (`scripts/ci/prod_image_prune_plan.py`). It reads the repository from `RepoDigests` because an
  image whose tag moved on has none of its own. `PRUNE_DRY_RUN=1` lists without removing.
- **Disk pre-check.** The first remote step of `deploy.sh` refuses to go on when less than
  `DEPLOY_MIN_FREE_GB` (default 8) is free on `DEPLOY_DISK_CHECK_PATH` (default `/`). The error
  names the free space and the fix; nothing has been pulled, dumped or migrated at that point.
- **Dump before recreate.** The prepare step now only ever starts a missing `db`
  (`--no-recreate`). `DEPLOY_DB=1` pulls and recreates `db` in a new step 3, between the verified
  dump and the migrations. The final `up` never touches `db` any more.
- **Upgrade.** `db` sets `MARIADB_AUTO_UPGRADE: "1"`, the image's documented switch: on a
  newer server its entrypoint backs the system tables up to `system_mysql_backup_*.sql.zst` in the
  data directory and runs `mariadb-upgrade`. The readiness wait now pings over TCP
  (`--protocol=tcp -h 127.0.0.1`), which only the real server answers. After a recreate the deploy
  prints the entrypoint's upgrade log and requires `mariadb_upgrade_info` to match the server's
  major.minor, stopping before any migration otherwise. The image is pinned as
  `mariadb:13.0.2@sha256:...`, and `mariadb` is added to Renovate's `pinDigests` rule (it was not
  covered) with its own label for minor/major moves. The same pin is in the core, full and test
  compose files.
- **Tunnel advice.** Dropped from `muma-ops docs/deployment-production.md`. The MCP needs `DB_BIND_ADDRESS=203.0.113.10`.
  A second account at `'172.22.%'` would work, but it would let every container on that bridge
  log in as the read-only user, and the subnet is only stable until the network is recreated.
  `DB_BIND_ADDRESS` is **not** added to `release:check-secrets`: production works without it, and
  only a workstation tool needs it. A `DEPLOY_DB=1` deploy without it now prints a note instead,
  since that is the moment the MCP loses the database.

Tests: `tests/ci/test_prod_image_prune_plan.py` covers the planner.
`tests/ci/test_deploy_disk_and_db_safety.py` covers the disk check, the dump-then-recreate order,
the upgrade check, the TCP readiness, the digest pin and Renovate rule, and the prune script
against a fake host. The existing deploy-order tests in `tests/ci/test_deploy_script_hygiene.py`
are updated.
