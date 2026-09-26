- **A deploy no longer fills the production disk, and `DEPLOY_DB=1` backs the database up before
  it replaces it.** After a verified deploy, `scripts/ci/prune-prod-images.sh` removes images that
  no container uses. It keeps the three previous images of each repository for an `IMAGE_TAG`
  rollback, plus `:latest`/`:stable`/`:rc`. It never uses `docker rmi -f` and logs the free space
  before and after. On 2026-09-26 old images had filled the root disk to 95%. `deploy.sh` now
  refuses to start with less than 8 GB free (`DEPLOY_MIN_FREE_GB`). `DEPLOY_DB=1` recreates `db`
  after the verified pre-deploy dump rather than before it. `db` now runs
  `mariadb:13.0.2@sha256:...` with `MARIADB_AUTO_UPGRADE=1`, so the coming 12.3 -> 13.0 move runs
  `mariadb-upgrade`. The deploy waits for the real server over TCP, logs the upgrade and checks
  it before any migration. Renovate now keeps the MariaDB digest current. `docs/deployment.md` no
  longer offers an ssh tunnel for the read-only MCP, because the `muma-readonly@'192.0.2.1.%'`
  account cannot log in through one. Bug report 094.

<!-- release notes -->

- **Deploys clean up old server images**, so the production disk no longer fills up release by
  release. Database upgrades now always happen after a fresh backup.
