# Self-hosting

How to run the stack on your own server and how a GitLab CI pipeline can deploy it. The examples
use `example.org` and `203.0.113.10`, replace them with your own values.

## What runs

Two Docker Compose stacks:

- `docker/docker-compose.yml` holds MariaDB, phpMyAdmin, `music-manager` (API, tagger and scanner)
  and the source workers.
- `services/music-management-server/docker-compose.yml` holds the player (`lms`) and its reverse
  proxy. It is its own stack and has its own `.env`.

Both join the external Docker network `music-management_db`, so `music-manager` reaches `lms` by
container name.

## Configure the stack

Copy `.env.example` to `.env` and fill it in. The keys you must set:

| Key | What it is |
|---|---|
| `DB_PASS`, `MYSQL_ROOT_PASSWORD` | Database passwords. |
| `MUMA_API_KEY` (or `API_KEY`) | The shared key between services. Without it every service call is refused. |
| `HOST_MUSIC_PATH`, `HOST_DATA_PATH` | Where your music and the database files live on the host. |
| `DOCKER_USER` | The registry account the images are named under, for example `example-user`. |
| `GOOGLE_CLIENT_ID` | Only for "Sign in with Google". Must equal `VITE_GOOGLE_CLIENT_ID` in the player's `.env`. |
| `FIREFOX_PASSWORD` | The login of the `firefox` container, which has no default. |
| `COMPOSE_PROFILES` | Which source workers run, see below. |

`.env.example` lists the other keys with a comment each. Settings you can change at runtime are on
the Beheer > Config page and win over the environment.

Start the stack:

```
docker-compose -f docker/docker-compose.yml --env-file .env up -d
```

## Source workers are compose profiles

The importer and the downloaders only run when you enable their profile:

| Profile | Services |
|---|---|
| `importer` | `importer_worker` |
| `youtube` | `youtube_worker` |
| `soundcloud` | `soundcloud_worker`, `soundcloud-fetcher` |
| `telegram` | `telegram_worker` |

Put the profiles you want in `.env`:

```
COMPOSE_PROFILES=importer,youtube
```

A stack without a profile runs the database, the manager and the other core services, and no worker.
`scripts/deploy.sh` stops before it changes anything when the compose file declares profiles and the
env file has no `COMPOSE_PROFILES` line. It skips a service whose profile is off, but it does not stop
a container of a profile you removed: stop that one yourself. Profiles need compose 1.28 or later.

A one-off command on a profiled service needs the profile too:

```
docker-compose -f docker/docker-compose.yml --profile soundcloud run --rm soundcloud-fetcher
docker-compose -f docker/docker-compose.yml --profile importer logs -f importer_worker
```

## Migrations

`scripts/deploy.sh` applies every `migrate_*.sql` file in the repository root before it starts the
new containers. `tools/apply_migrations.py` does the work.

- Files run in byte-wise order of their names. That puts `migrate_v10_audio_features_relink.sql` before `migrate_v2.sql`.
  A migration must not depend on a higher-numbered one.
- The `schema_migrations` table records each file with its sha256. A recorded file is skipped, a
  changed file runs again. Every migration must still be safe to run twice.
- Each file runs under a lock wait timeout of `MIGRATION_LOCK_WAIT_SECONDS` (default 120). A
  statement that waits longer fails, and the deploy stops while the old release keeps serving. Find
  the session that holds the lock with `SHOW PROCESSLIST` as the database root user, end it, and
  deploy again.
- Migrations are expand-only. The old release is still running while they apply, so add tables,
  columns and indexes, and drop, rename or narrow nothing the old code reads. Do that in a later
  release. `tests/ci/test_migration_ordering.py` enforces it.

A schema change needs the `CREATE TABLE` in `services/common/db_init.py` and a re-runnable
`migrate_*.sql` with the same shape. See [AGENTS.md](../AGENTS.md).

## Backups

`tools/db_backup.py` writes a verified `mariadb-dump` to `HOST_BACKUP_PATH`, which must be on another
disk than `HOST_DATA_PATH`. Systemd timers run it nightly, alert when the newest dump is older than
`BACKUP_STALE_AFTER_HOURS` and restore the newest dump into a throwaway database every Sunday to
check it. Install them with `scripts/backup/install-systemd.sh`. Details are in
[scripts/backup/README.md](../scripts/backup/README.md).

Every remote deploy takes a pre-deploy dump first and keeps the newest three. No verified dump means
no deploy. `PREDEPLOY_BACKUP=0` skips it for an emergency.

To restore a dump into a database you name:

```
scripts/restore_db.sh /mnt/backups/muma/muma_db_<stamp>.sql.gz <target-database>
```

The script refuses to restore over the live database (`DB_DB`) or into a non-empty one without `--force`.

## Roll back

Every image is referenced as `${IMAGE_TAG:-latest}` and each release pushes `:<version>`. To go back:

```
IMAGE_TAG=0.72.0 ./scripts/deploy.sh
```

The old release runs on the current schema because migrations are expand-only. The deploy takes its
own pre-deploy dump first.

## Deploy from GitLab CI

A pipeline on a `release/*` branch builds the images, deploys over SSH with `scripts/ci-deploy.sh`
and checks `/health` afterwards. Set these in Project > Settings > CI/CD > Variables.
`scripts/ci/check-required-secrets.sh` (job `release:check-secrets`) fails the pipeline when a
required one is missing.

| Variable | Purpose |
|---|---|
| `SSH_PRIVATE_KEY` | Key of a deploy user on the target host. |
| `PROD_REMOTE_HOST` | Host name or address, for example `203.0.113.10`. No default. |
| `PROD_REMOTE_USER` | Login on the host. Optional, default `root`. |
| `PROD_SSH_KNOWN_HOSTS` | File type. The host's public keys in `known_hosts` format, under the same string as `PROD_REMOTE_HOST`. Without a pinned key the deploy stops. `PROD_SSH_ACCEPT_NEW_HOST_KEY=true` accepts the key on first use instead. |
| `PROD_URL` | Public address of the stack, for example `https://music.example.org`. Used as the environment URL. |
| `PROD_ENV_FILE` | File type. The full `.env` of the `music-management` stack. |
| `PROD_ENV_FILE_LMS` | File type. The full `.env` of the player stack. |
| `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` | Registry login the images are pushed with. The username must equal `DOCKER_USER` in `PROD_ENV_FILE`. |
| `TAG_CREATION_TOKEN` | Project access token (Maintainer, `api` scope) that creates release tags and the back-merge. |

Keys the check requires inside `PROD_ENV_FILE`: `GOOGLE_CLIENT_ID`, `API_KEY` or `MUMA_API_KEY`,
`DOCKER_USER`, `COMPOSE_PROFILES` and `FIREFOX_PASSWORD`. Inside `PROD_ENV_FILE_LMS`:
`VITE_GOOGLE_CLIENT_ID`. Add a key to `scripts/ci/check-required-secrets.sh` and to this list when a
new secret becomes required.

`scripts/deploy.sh` sends the env file over SSH on stdin, never on a command line, and the host keeps
it only while the deploy runs.

### Android app build

The app takes its server address from build settings. A release build stops without the first two:

| Variable | Purpose |
|---|---|
| `MUMA_SERVER_URL` | The server the app talks to, for example `https://music.example.org`. |
| `MUMA_GOOGLE_CLIENT_ID` | The Web client id of "Sign in with Google". |
| `MUMA_API_URL` | Optional. A separate host for the MuMa API. The CI release script also needs it. |
| `MUMA_OWN_DOMAIN` | Optional. Your domain, for example `example.org`. Servers on it, and its subdomains, use `MUMA_API_URL`. The CI release script also needs it. |

A build without these uses `https://music.example.org` and hides the Google button.
