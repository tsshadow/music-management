# Self-hosting

How to run the stack on your own server and how a GitLab CI pipeline can deploy it. The examples
use `example.org` and `203.0.113.10`, replace them with your own values.

## What runs

Two Docker Compose stacks:

- `docker/docker-compose.yml` holds MariaDB, phpMyAdmin, `music-manager` (API, tagger and scanner)
  and the source workers.
- `services/music-management-server/docker-compose.yml` holds the player (`lms`) and its reverse
  proxy. It is its own stack and has its own `.env`.

The main stack creates the Docker network `music-management_db`. The player stack declares it as
`external`, so start the main stack first. Then `music-manager` and `lms` reach each other by
container name.

## Host requirements

- Docker, and either the Compose plugin (`docker compose`) or `docker-compose` 1.28 or later. Profiles
  need 1.28. `scripts/deploy.sh` uses the plugin when it exists.
- For a deploy over SSH: a login that can run `docker` on the host (root in the examples), and the
  `ssh` client (plus `sshpass` only if you use `REMOTE_PASS` instead of a key) on the machine that
  runs the script.
- The host needs no checkout. `scripts/deploy.sh` ships the compose file and the env file itself and
  keeps them under `~/.muma-deploy/<stack>/` of the deploy user. A checkout of this repository is only
  needed on the machine you deploy from, and for the backup timers (see Backups).
- The directories `HOST_MUSIC_PATH`, `HOST_DATA_PATH` and `HOST_BACKUP_PATH` exist on the host.

## Configure the stack

Copy `.env.example` to `.env` and fill it in. The keys you must set:

| Key | What it is |
|---|---|
| `DB_DB`, `DB_USER`, `DB_PASS` | Name, user and password of the application database. |
| `MYSQL_ROOT_PASSWORD` | Database root password. Migrations and the fallback dump use root when it is set. |
| `DB_BIND_ADDRESS` | Address MariaDB publishes port 3306 on. Default `127.0.0.1`. Set a LAN address, for example `203.0.113.10`, only if another machine must reach the database. |
| `MUMA_API_KEY` (or `API_KEY`) | The shared key between services. Without it every service call is refused. |
| `HOST_MUSIC_PATH`, `HOST_DATA_PATH` | Where your music and the database files live on the host. |
| `HOST_BACKUP_PATH` | Where the database dumps go. Required by `scripts/backup/install-systemd.sh`, and it must be on another disk than `HOST_DATA_PATH`. |
| `DOCKER_USER` | The registry account the images are named under, for example `example-user`. |
| `GOOGLE_CLIENT_ID` | Only for "Sign in with Google". Must equal `VITE_GOOGLE_CLIENT_ID` in the player's `.env`. |
| `FIREFOX_PASSWORD` | The login of the `firefox` container, which has no default. |
| `COMPOSE_PROFILES` | Which source workers run, see below. |

`.env.example` lists the other keys with a comment each. Settings you can change at runtime are on
the Beheer > Config page and win over the environment.

Start the main stack first:

```
docker-compose -f docker/docker-compose.yml --env-file .env up -d
```

### The player stack

`services/music-management-server/docker-compose.yml` has its own env file. Keys it reads:

| Key | What it is |
|---|---|
| `IMAGE_NAME`, `LMS_TAG` | The player image and its tag, for example `example-user/lms` and `0.72.0`. |
| `MUSIC_PATH` | Your music folder on the host. Default `/music`. |
| `DOCKER_DATA_PATH` | Parent of the player's data (`lms/var/lms`, `lms/usr/local/etc`, `lms/nginx`). Default `/docker`. |
| `LMS_API_KEY`, `LMS_SUBSONIC_API_KEY` | Keys of the player's own API and of the Subsonic API. |
| `MUSIC_MANAGEMENT_URL`, `MUSIC_MANAGEMENT_API_KEY` | Where `music-manager` answers (`http://music-manager:8000/api`) and the shared key, the same value as `MUMA_API_KEY` above. |
| `LMS_PORT`, `LMS_SUBSONIC_PORT` | Published ports of the web UI (default 80) and the Subsonic API (default 8080). |
| `VITE_GOOGLE_CLIENT_ID` | Build-time only, for "Sign in with Google". |

Start it after the main stack:

```
docker-compose -f services/music-management-server/docker-compose.yml --env-file lms.env up -d
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

## Deploy by hand

`scripts/deploy.sh` deploys the main stack to a remote host over SSH. It reads `.env` in the
repository root (or the file named in `LOCAL_ENV_FILE`) and needs these keys in it:

```
REMOTE_HOST=203.0.113.10
REMOTE_USER=root
DOCKER_USER=example-user
DEPLOY_TARGET_NAME=music-management
```

`REMOTE_PASS` is optional, without it SSH uses your key. Set `DEPLOY_TARGET_NAME` to
`music-management`: without it the script uses the project name `muma`, which is a second compose
project next to yours. The script takes one optional argument, a service name (`manager` stands for
`music-manager`), to update only that service. It exits with an error when `REMOTE_HOST` or
`REMOTE_USER` is missing.

```
./scripts/deploy.sh
./scripts/deploy.sh manager
```

The order is: check the disk, start `db` if it is missing, take a verified dump, apply the
migrations, then pull and recreate the containers whose image or definition changed.

| Variable | Effect |
|---|---|
| `DEPLOY_DB=1` | Also recreates the `db` container when its definition changed, after the dump. Without it `db` is never recreated. |
| `DEPLOY_MIN_FREE_GB` | Refuses to start when less than this is free (default 8) on `DEPLOY_DISK_CHECK_PATH` (default `/`). Free space first: `docker system df`, then `docker image prune -a -f --filter until=72h` on the host. |
| `DEPLOY_ONESHOTS=1` | Also starts the one-shot containers `soundcloud-fetcher` and `genre-processor`. |
| `IMAGE_TAG=<tag>` | Deploys that tag of every image instead of `:latest`. |
| `PREDEPLOY_BACKUP=0` | Skips the dump, loudly. For an emergency only. |

## Roll back

Every image is referenced as `${IMAGE_TAG:-latest}` and each release pushes `:<version>`. Run the
deploy with the old tag, from the same `.env` as above:

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
| `APK_HOSTER_URL`, `APK_HOSTER_PASSWORD` | Address and password of the service that hosts the APK. Only for the Android jobs. |
| `SIGNING_STORE_FILE` | File type. The release keystore, base64-encoded (`base64 -w0`). Only for the Android release job. |
| `SIGNING_STORE_PASSWORD`, `SIGNING_KEY_ALIAS`, `SIGNING_KEY_PASSWORD` | Keystore password, key alias and key password. Only for the Android release job. |
| `TAG_CREATION_TOKEN` | Project access token (Maintainer, `api` scope) that creates release tags and the back-merge. |

`release:check-secrets` requires `PROD_REMOTE_HOST`, `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`,
`APK_HOSTER_URL` and `SIGNING_STORE_FILE`, because a job gated on a missing variable silently
drops out of the pipeline instead of failing. The Android jobs (`mobile:build-debug`,
`mobile:build-release`) run only when `APK_HOSTER_URL` is set, and the release job also needs
`SIGNING_STORE_FILE`. If you do not ship an Android app, remove that part of the check in
`scripts/ci/check-required-secrets.sh` (the `APK_HOSTER_URL` and `SIGNING_STORE_FILE` lines) and
leave both variables unset.

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
