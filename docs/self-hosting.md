# Self-hosting

How to run the stack on your own server and how a GitLab CI pipeline builds and publishes it. The examples
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
| `PUBLIC_SOURCE_URL` | Where users get the source code (AGPL-3.0 section 13), shown as the Source code link on the About and login screens. Default `https://github.com/OWNER/music-management`, a placeholder: set your own repository or fork. |
| `FIREFOX_PASSWORD` | The login of the `firefox` container, which has no default. |
| `FIREFOX_BIND_ADDRESS` | Address the `firefox` container publishes its port 7003 on. Default `127.0.0.1`. Set `0.0.0.0` or a LAN address if you open the browser from another machine. |
| `MUSIC_MANAGER_BIND_ADDRESS` | Address `music-manager` publishes its API on (ports 8000 and 8003). Default `127.0.0.1`. Browsers and apps reach the API through the player's nginx at `/muma/api/`, and the other containers through the Docker network, so neither needs it. Set a LAN address only for a tool on another machine that must call port 8000 directly, and know that it then skips nginx. |
| `/health` | Not a variable. A monitor such as Uptime Kuma checks `https://<your domain>/health`, which the player's nginx passes to `music-manager`. It answers 200 when healthy and 503 when not. Without an `X-API-Key` header the body is `status` and `source_url` only; send the system key for the full report. |
| `/health/backup` | Not a variable. The player's nginx passes it to `music-manager` the same way. It needs no key, answers 200 when the newest database backup is younger than `BACKUP_STALE_AFTER_HOURS` (default 36) and 503 when it is older or missing. |
| `MIRROR_STATUS_PATH` | Optional. Where music-manager reads the music mirror's `latest.json` for `GET /health/music-mirror` and the daily check, as a path inside the container: `/backups/music-mirror` once the mirror runs (issue #25, `scripts/music-mirror/README.md`). Empty answers 503 `unconfigured`. `MIRROR_STALE_AFTER_HOURS` (default 36) is the age at which a good run counts as stale. The endpoint needs no key and never shows a file name. |
| `AUTH_TRUSTED_PROXIES` | Optional. The networks whose `X-Forwarded-For` header the login rate limit believes. Default `127.0.0.0/8,::1/128,connected`, where `connected` means the Docker networks the `music-manager` container is attached to: the nginx and LMS that sit in front of it. A LAN address is not trusted. |
| `COMPOSE_PROFILES` | Which source workers run, see below. |

Three more paths of the main stack decide where `music-manager` finds the player's data. Set them in
`.env` when your player data is not under `/docker`:

| Key | What it is |
|---|---|
| `LMS_DATA_PATH` | The player's data folder, mounted into `music-manager` to read `var/lms/lms.db`. Default `/docker/lms`. Match `${DOCKER_DATA_PATH}/lms` of the player stack. |
| `ALPHA_LMS_DATA_PATH` | Same for a second (alpha) player. Default `/docker/alpha-lms`. Leave it when you run one player. |
| `NEWS_DATA_PATH` | Where the hourly news bulletins are written. Default `/docker/muma-news`. |

`.env.example` lists the other keys with a comment each. Settings you can change at runtime are on
the Management > Configuration page and win over the environment.

Compose reads `.env` from the folder of the compose file, which is `docker/`, not the checkout
root. Pass `--env-file .env` as in the commands below, or the stack starts with every variable blank.

The image names (`IMAGE_CORE`, `IMAGE_IMPORTER`, `IMAGE_DOWNLOADER`, `IMAGE_TELEGRAM`, `IMAGE_TOOLS`,
`IMAGE_BASE`) have working defaults in `.env.example`. A production `.env` sets its own values, and
they win.

### Build the images

On a single host with no registry, build the images there. `./build.sh` reads `.env`, builds the
base image and then `music-manager`, the importer, the downloader, the Telegram worker, the tools
and the player. It does not push anything. `--skip-lint --skip-test` skips the pylint and pytest
runs, which need Python tooling on the host:

```
./build.sh --skip-lint --skip-test
```

The images are tagged `${DOCKER_USER}/${IMAGE_...}:latest` and `:<VERSION>`, so `muma/music-manager`
with the defaults. To build one part, name it: `./build.sh manager importer`. The player image is
`${DOCKER_USER}/music-management-server`, which is what `IMAGE_NAME` in the player's env file
(below) must point at. Do not run `./install.sh` for this: it also publishes to Docker Hub and
deploys over SSH.

### Start the stack

Start the main stack first:

```
docker-compose -f docker/docker-compose.yml --env-file .env up -d
```

### The player stack

`services/music-management-server/docker-compose.yml` has its own env file. Keys it reads:

| Key | What it is |
|---|---|
| `IMAGE_NAME`, `LMS_TAG` | The player image and its tag. After `./build.sh`, `muma/music-management-server` and `latest` (use your `DOCKER_USER`). |
| `MUSIC_PATH` | Your music folder on the host. Default `/music`. |
| `DOCKER_DATA_PATH` | Parent of the player's data (`lms/var/lms`, `lms/usr/local/etc`, `lms/nginx`). Default `/docker`. |
| `reverse-proxy.conf` | Not a variable. Copy `services/music-management-server/nginx/reverse-proxy.conf` to `${DOCKER_DATA_PATH}/lms/nginx/reverse-proxy.conf` before the first start. The `reverse-proxy` container mounts that file, and Docker creates a directory in its place when it is missing. |
| `LMS_API_KEY`, `LMS_SUBSONIC_API_KEY` | Keys of the player's own API and of the Subsonic API. |
| `MUSIC_MANAGEMENT_URL`, `MUSIC_MANAGEMENT_API_KEY` | Where `music-manager` answers (`http://music-manager:8000/api`) and the shared key, the same value as `MUMA_API_KEY` above. |
| `LMS_PORT`, `LMS_SUBSONIC_PORT` | Published ports of the web UI (default 80) and the Subsonic API (default 8080). |
| `NGINX_TRUSTED_PROXY` | The reverse proxy on your LAN that sends requests to the `reverse-proxy` container, for example `192.0.2.30`. A comma or space separated list of addresses or CIDRs. nginx takes the client address from `X-Forwarded-For` only when the request comes from loopback, a Docker network (172.16.0.0/12) or an entry here. Empty by default. Set it when a proxy such as Nginx Proxy Manager sits in front, or MuMa's login rate limit counts every login against the proxy's address. Do not set a LAN range: any host in it could then name its own client address. A value that is not an address or a CIDR stops the container at start. Docker networks outside 172.16.0.0/12 (a custom address pool) go here too. |
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
| `youtube` | `youtube_worker`, `firefox` |
| `soundcloud` | `soundcloud_worker`, `soundcloud-fetcher`, `firefox` |
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

## The music folder

The tagger finds files by folder name under `music_folder_path`, not by the `*_folder` settings:

| Folder | What the tagger takes it for |
|---|---|
| `Soundcloud/<channel>` | SoundCloud downloads, one folder per channel |
| `Youtube/<channel>` | YouTube downloads, one folder per channel |
| `Telegram/<channel>` | Telegram downloads, one folder per channel |
| `Livesets`, `Podcasts`, `Top 100`, `Warm Up Mixes` | Sets and mixes, tagged from their file names |
| `EPs` (`eps_folder_path`) | Label releases, `<label>/<release>`; the import queue is `__TODO` inside it |

`youtube_folder`, `soundcloud_folder` and `telegram_folder` tell the downloaders where to write.
Point them at the folders above: a download written anywhere else is never tagged.

## First start and logins

### First admin

A new database has no accounts. Open the web player: while the `users` table is empty, the login page
shows a form for the first account. It calls `POST /api/auth/setup` (unauthenticated) and creates that
account as admin. The call answers `409` once any account exists. See `docs/authentication.md`.

### Sign in with Google (optional)

Skip this and the Google button stays hidden; username and password still work.

1. In the Google Cloud Console, create a project and configure the OAuth consent screen.
2. Create an OAuth client of type "Web application". Its client id is the Web client id.
3. Set that one value in three places: `GOOGLE_CLIENT_ID` in `.env` (the manager checks the token
   audience against it), `VITE_GOOGLE_CLIENT_ID` in the player's `.env` (a build argument, so rebuild the
   player image), and `MUMA_GOOGLE_CLIENT_ID` for the Android build.
4. Add your player's address to the "Authorized JavaScript origins" of that client.
5. For the app, create a second OAuth client of type "Android" with the app's package name and the
   SHA-1 of your signing key. The app still requests its token with the Web client id; the Android
   client only lets Google accept the app.

`MUMA_GOOGLE_CLIENT_ID` is read from the environment or from the Gradle property `muma.googleClientId`
(for example in `~/.gradle/gradle.properties`). A release build without it stops.

### SoundCloud and YouTube cookies

The SoundCloud and YouTube workers read the cookies of a logged-in Firefox. That browser is the
`firefox` container, which starts with either profile.

1. Set `FIREFOX_PASSWORD`, start the stack and open `https://<host>:7003` (the container uses a self-signed
   certificate). Log in with `FIREFOX_USER` (default `admin`) and the password. The port listens on
   `127.0.0.1` only unless you set `FIREFOX_BIND_ADDRESS`.
2. In that browser, log in to soundcloud.com and youtube.com with your account.
3. The profile is saved under `${HOST_DATA_PATH}/firefox`, which the workers mount read-only.

Respect the terms of the platforms, and download only what you may.

### Telegram

The Telegram worker needs `telegram_api_id` and `telegram_api_hash` (from my.telegram.org) in `.env`,
and a one-time interactive login:

```
./run_telegram_auth.sh "<channel name>"
```

Run it from the repository root. It asks for your phone number and the code Telegram sends, and saves
the session in the data volume. The default channel name in the script, `Hard Dance Events`, is only an
example: always pass the channel you want. Then start the worker with the `telegram` profile.

### Android app and the server address

The server address is compiled into the app (`MUMA_SERVER_URL`, see "Android app build"). The app
refuses cleartext `http://` to every host except `localhost` and `127.0.0.1`
(`network_security_config.xml`). A server on your LAN therefore needs `https://`: put a reverse proxy
with a certificate in front of it and build the app with that address. You can hand the APK to users in
any way you like, for example GitHub Releases or by sideloading.

## Schema changes

`services/common/schema_tables.py` declares every table and view of the database. A new stack gets
them from it, with the seed rows in `services/common/seeds/`, when music-manager starts.

On each deploy, `scripts/deploy.sh` runs the `schema-reconcile` one-shot from the image it deploys,
before it starts the new containers. It builds the declaration in a scratch database
(`<DB_DB>_schema_probe`), compares it with the live database, and adds the tables, columns, indexes
and views the live database does not have. It changes and drops nothing. It prints every other
difference as a `report:` line and leaves it alone. `--dry-run` prints the statements and runs none.

- Each statement waits at most `SCHEMA_LOCK_WAIT_SECONDS` (default 120) for a lock. A statement that
  waits longer fails, and the deploy stops while the old release keeps serving. Find the session
  that holds the lock with `SHOW PROCESSLIST` as the database root user, end it, and deploy again.
- A unique index that the data violates also stops the deploy. The error names the table and the
  index. Remove the duplicate rows and deploy again.
- The old release still runs while the reconcile adds, so a new column needs a default or must
  allow `NULL`.

A change the reconcile cannot make (drop, rename, change a type, a new foreign key on existing
data) needs a script in `tools/` with a dry run and a backup, like `tools/schema_cleanup_2026_11.py`.
Change the declaration in the same merge request, and list the difference in
`tests/integration/test_schema_snapshot.py` until the script has run on production.

**Upgrade from 0.93 or older.** The migration files are gone. An installation older than 0.93.0
must deploy a 0.93.x release first, then this one.

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

The order is: check the disk, start `db` if it is missing, take a verified dump, add what the
schema lacks, then pull and recreate the containers whose image or definition changed.

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

The old release runs on the current schema because the reconcile only adds. The deploy takes its
own pre-deploy dump first.

## Build and publish from GitLab CI

A pipeline on a `release/*` branch builds the images and the APK. Merging it to `master` tags
`release-vX.Y.Z` once `release:publish` has found both. The pipeline deploys nothing and holds no
production host, SSH key or env file: your installation deploys a tag with its own settings, for
example with `scripts/deploy.sh` as above
([docs/designs/ops-split/](designs/ops-split/functional.md)). Set these in Project > Settings >
CI/CD > Variables. `scripts/ci/check-required-secrets.sh` (job `release:check-secrets`) fails the
pipeline when a required one is missing.

| Variable | Purpose |
|---|---|
| `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN` | Registry login the images are pushed with. Required. |
| `DOCKER_USER` | Optional. The registry user the images are named under, default `DOCKERHUB_USERNAME`. When set, it must equal it. |
| `IMAGE_CORE`, `IMAGE_BASE`, `IMAGE_DOWNLOADER`, `IMAGE_TELEGRAM`, `IMAGE_IMPORTER`, `IMAGE_TOOLS`, `IMAGE_LMS` | Optional. Image names, defaults in `scripts/ci/release-image-names.sh` (`music-manager`, `muma-base`, `muma-downloader`, `muma-telegram`, `muma-importer`, `muma-tools`, `lms`). Your `.env` files must pull the same names: `IMAGE_*` and `IMAGE_NAME=<DOCKER_USER>/<IMAGE_LMS>` for the player. |
| `VITE_GOOGLE_CLIENT_ID` | Optional. The Web client id of "Sign in with Google", compiled into the player image. Default `MUMA_GOOGLE_CLIENT_ID`. One of the two is required. |
| `APK_HOSTER_URL` | Address of the service that hosts the APK, built into the app. Only for the Android jobs. |
| `APK_HOSTER_PASSWORD` | Upload password of that service. Only for `mobile:build-debug`; the release APK goes to the package registry and the installation uploads it. |
| `SIGNING_STORE_FILE` | File type. The release keystore, base64-encoded (`base64 -w0`). Only for the Android release job. |
| `SIGNING_STORE_PASSWORD`, `SIGNING_KEY_ALIAS`, `SIGNING_KEY_PASSWORD` | Keystore password, key alias and key password. Only for the Android release job. |
| `TAG_CREATION_TOKEN` | Project access token (Maintainer, `api` scope) that pushes the release tags (made with `git tag -a` as `ci-release-tagging`, so the tagger is not the token's bot user) and pushes the back-merge of master into develop (a merge commit made with git as `ci-release-tagging`, so a Maintainer token must be allowed to push to develop), and reads the release pipeline for `release:publish`. |

`release:check-secrets` requires `DOCKERHUB_USERNAME`, `DOCKERHUB_TOKEN`, `APK_HOSTER_URL`,
`SIGNING_STORE_FILE`, and `VITE_GOOGLE_CLIENT_ID` or `MUMA_GOOGLE_CLIENT_ID`, because a job gated on
a missing variable silently drops out of the pipeline instead of failing, and a player built without
the client id has no Google button. The Android jobs (`mobile:build-debug`, `mobile:build-release`)
run only when `APK_HOSTER_URL` is set, and the release job also needs `SIGNING_STORE_FILE`. If you
do not ship an Android app, remove that part of the check in `scripts/ci/check-required-secrets.sh`
(the `APK_HOSTER_URL` and `SIGNING_STORE_FILE` lines) and leave both variables unset. Add a variable
to that script and to this list when a new one becomes required for a release.

Your deploy, not this pipeline, checks the env files. The keys a working stack needs: in the
`music-management` `.env`, `GOOGLE_CLIENT_ID`, `API_KEY` or `MUMA_API_KEY`, `DOCKER_USER`,
`COMPOSE_PROFILES` and `FIREFOX_PASSWORD`; in the player's `.env`, `LMS_API_KEY`,
`LMS_SUBSONIC_API_KEY` and `MUSIC_MANAGEMENT_API_KEY`. `scripts/deploy.sh` sends the env file over
SSH on stdin, never on a command line, and the host keeps it only while the deploy runs.

### Android app build

The app takes its server address from build settings. A release build stops without the first two:

| Variable | Purpose |
|---|---|
| `MUMA_SERVER_URL` | The address a fresh install suggests on its first-run screen, for example `https://music.example.org`. |
| `MUMA_GOOGLE_CLIENT_ID` | The Web client id of "Sign in with Google". |
| `MUMA_API_URL` | Optional. A separate host for the MuMa API. The CI release script also needs it. |
| `MUMA_OWN_DOMAIN` | Optional. Your domain, for example `example.org`. Servers on it, and its subdomains, use `MUMA_API_URL`. The CI release script also needs it. |

A build without these suggests no address: the app asks for the server on its first start, and it hides
the Google button. Google sign-in only shows for the build's own server.
