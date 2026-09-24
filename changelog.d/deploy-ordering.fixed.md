- **A deploy started the new code before its migrations, with no backup and no way back.**
  `scripts/deploy.sh` recreated every container first — MariaDB included, with `--force-recreate`
  — and migrated afterwards, and `release:build-images` had already pushed `:latest`, which
  Watchtower on the host pulls for the downloader images, so a release's workers could start before
  `muma:deploy` had migrated anything, or without any deploy at all when it was skipped. The order
  is now: database up and answering, a verified pre-deploy dump (`tools/db_backup.py` with
  `BACKUP_LABEL=pre-deploy`, else `mariadb-dump` through `docker exec`; no dump, no deploy),
  migrations while the previous release still runs, `:latest` moved from `:${VERSION}` inside
  `muma:deploy`, then `pull` + `up` of only what changed. `db` is no longer recreated on a routine
  deploy (`DEPLOY_DB=1` does), the one-shot `soundcloud-fetcher`/`genre-processor` no longer run on
  every deploy (`DEPLOY_ONESHOTS=1`), and every image this repo builds is
  `${IMAGE_TAG:-latest}`, so `IMAGE_TAG=<previous> ./scripts/deploy.sh` is a rollback. New
  migrations must be expand-only (`tests/ci/test_migration_ordering.py`). See bug report 050.
- **The post-deploy check could pass while a container was crash-looping.** It sampled once, right
  after `up`. music-manager now has a healthcheck on `/health`, every worker a light one (Python
  runs, MariaDB reachable), and `post-deploy-verify.sh` probes LMS's Subsonic ping and re-samples
  after 60 s, failing on any restart-count increase or unhealthy container.
- **CI tested on Python 3.11 against whatever the runner had installed; production runs 3.14.**
  `backend:unit` and `backend:integration` now run inside `docker/Dockerfile.python-ci`
  (python:3.14-slim) with `requirements.txt` installed, and the lint jobs always use their 3.14
  container. That run found `httpx2` missing from `requirements.txt` and a numpy stub that broke
  every property-based test; both are fixed.
- **Changed production defaults (need a human on the first deploy).** MariaDB `3306` and phpMyAdmin
  `8002` bind to `127.0.0.1` unless `DB_BIND_ADDRESS`/`PHPMYADMIN_BIND_ADDRESS` are set (the database
  binding only changes on a `DEPLOY_DB=1` deploy; phpMyAdmin's on the next one). The Firefox noVNC
  password lost its `admin` default and `FIREFOX_PASSWORD` is now required in `PROD_ENV_FILE` by
  `release:check-secrets`. Every service's log is capped at 3 × 10 MB, and music-manager (4g) and
  the workers (2g, telegram 1g) have memory limits, overridable per `MUMA_MEM_LIMIT_*`.

<!-- release notes -->

- **Deploys are safer.** The database is backed up and migrated before any new code starts, a
  deploy no longer restarts the database, and a bad release can be rolled back by redeploying the
  previous version's images. The post-deploy check now notices a service that keeps restarting.
- **Database and phpMyAdmin are no longer reachable from the whole network by default**, the
  Firefox helper needs a real password, and container logs and memory are capped.
