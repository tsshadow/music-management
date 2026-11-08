# Music Management System

[![license](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

MuMa downloads, imports, tags and plays your music library. It is a set of services around one
MariaDB database: workers bring music in, a tagger fixes the metadata, a scanner keeps the database in
step with the files, and a Subsonic-compatible server streams it to a web player and an Android app.

It is built for one owner's collection of electronic music (hardcore, hardstyle and related genres),
so a number of defaults reflect that collection. See [Self-hosting](docs/self-hosting.md) to run your
own.

This GitHub repository is a read-only mirror. Development, issues and merge requests happen on the
maintainer's own GitLab, so issues are off here. To report a security problem, see
[SECURITY.md](SECURITY.md).

## The services

Core:
- **`frontend`** (`services/frontend`): the Svelte web player, with playback, library browsing and
  the Management pages for the tagger, scanner, users and workers.
- **`music-manager`** (`services/music_manager`): the FastAPI backend and the source of truth for
  metadata rules, ratings, listens and the event log. The tagger and the scanner run as threads
  inside it.
- **`music-management-server`** (`services/music-management-server`): the C++ streaming server and
  Subsonic API, a fork of [LMS](https://github.com/epoupon/lms).
- **MuMa Mobile** (`services/muma-mobile`): the Android app. It streams over the Subsonic API and
  stores its settings and ratings in `music-manager`. It is a normal APK, so hand it out any way you
  like.

Workers:
- **`importer`**: unpacks archives of bought or promo music and places them in the library.
- **`downloader`**: fetches tracks from YouTube and SoundCloud channels. Obey the platforms' terms of
  service and download only what you are allowed to.
- **`telegram`**: fetches files from Telegram chats you take part in.
- **`bpm-analyzer`**: measures the tempo of every track for browse by BPM.

`services/ml-analyzer` is deprecated and not built ([DEPRECATED.md](services/ml-analyzer/DEPRECATED.md)).

## Getting started

You need Docker and the Compose plugin (`docker compose`), or `docker-compose` 1.28 or later.

1. Clone the repository.
2. Copy `.env.example` to `.env` and fill in your paths, database credentials and keys.
3. Build the images on the host with `./build.sh --skip-lint --skip-test`.
4. Start the stack with `docker compose -f docker/docker-compose.yml --env-file .env up -d`.

[docs/self-hosting.md](docs/self-hosting.md) has the full steps: the keys, the source worker
profiles, the player stack, the nginx file and the first admin account.

`./build.sh` with no argument builds every image. Name one or more to build only those: `tools`,
`server`, `manager`, `downloader`, `telegram`, `importer` or `ml`. Without `--skip-lint --skip-test`
it runs pylint and the unit tests on the host first.

`install.sh`, `publish.sh` and `deploy.sh` push the images to a registry and deploy them to the
maintainer's host. They are not needed to run the stack.

When the stack is up:
- **Web player and Subsonic API**: port 8080 (`LMS_SUBSONIC_PORT`).
- **music-manager API**: port 8000.
- **phpMyAdmin**: port 8002, on the host's loopback only (`PHPMYADMIN_BIND_ADDRESS` opens it to the
  network).

### Users

Manage users on the Management pages of the web player. To set or reset a password from the
command line:

```bash
./scripts/set_user_password.sh <username>
```

The script asks for the password twice. `--password <pass>` also works, but the password then stays
in your shell history.

## Docker stacks

- **`docker/docker-compose.yml`**: MariaDB, phpMyAdmin, `music-manager`, the `bpm-analyzer`, the
  source workers and the Firefox container that holds the SoundCloud and YouTube logins.
- **`services/music-management-server/docker-compose.yml`**: the player (`lms`) and its reverse
  proxy, with its own env file.
- **`docker/docker-compose.tools.yml`**: one-off maintenance jobs, such as the release-date backfill
  and the genre processor.
- **`docker/docker-compose.workers.yml`**: a local overlay for `scripts/dev.sh`. It is not valid on
  its own.

### Source workers are opt-in

The workers that bring music into the library are Compose profiles. Without a profile, `up` starts
the database, the manager and the other core services, and none of the workers:

| Profile      | Services                                  | For                                                                  |
|--------------|-------------------------------------------|----------------------------------------------------------------------|
| `importer`   | `importer_worker`                         | Music you bought or got as a label promo, placed into your library.  |
| `soundcloud` | `soundcloud_worker`, `soundcloud-fetcher` | Tracks an artist or label published on their own SoundCloud channel. |
| `youtube`    | `youtube_worker`                          | Tracks an artist or label published on their own YouTube channel.    |
| `telegram`   | `telegram_worker`                         | Files from Telegram chats you take part in.                          |

Turn them on with `COMPOSE_PROFILES` in `.env`, for example `COMPOSE_PROFILES=importer,youtube`, or
per command with `docker compose --profile importer up -d`. See
[docs/self-hosting.md](docs/self-hosting.md#source-workers-are-compose-profiles).

To start the core services with every worker:

```bash
docker compose -f docker/docker-compose.yml \
  --profile importer --profile soundcloud --profile youtube --profile telegram up -d
```

A one-off command on a profiled service names its profile too, or Compose says the service does not
exist:

```bash
docker compose -f docker/docker-compose.yml --profile importer logs -f importer_worker
```

### Database backups

`./tools/backup_db.sh` writes a SQL dump of the running database container to `/muma/backups`, or to
`BACKUP_DIR` when you set it.

## Event log and alerts

Every service writes structured events (`INFO`/`WARNING`/`ERROR`/`CRITICAL`) to the `events` table.
That table is the source of truth: you can browse it on the Logs page of the web player and query it
with `GET /api/events` ([API specification](docs/api-specification.md)). Events come from four
sources: `music-manager` (which includes the tagger and scanner threads), `downloader`, `importer`
and `bpm-analyzer`.

[ntfy](https://ntfy.sh) is an optional push sink. The database keeps every event when ntfy is
unreachable. Two topics keep milestones and alerts apart:
- `notify_topic` (default `music-management`): download and import milestones, pushed only where
  the code asks for it.
- `notify_topic_alerts` (default `music-management-alerts`): every `WARNING` and higher, with
  `Priority: high` (`WARNING`/`ERROR`) or `urgent` (`CRITICAL`). A repeat from the same level,
  source and logger within five minutes is written to the database but not pushed again.

### Instant delivery on a self-hosted ntfy server

The ntfy Android app gets instant pushes through Firebase only for topics on `ntfy.sh` itself.
Against a self-hosted server it polls, so a `CRITICAL` alert can arrive minutes late. Add this line to
the ntfy server's `server.yml`:

```yaml
upstream-base-url: "https://ntfy.sh"
```

The self-hosted server then sends `ntfy.sh` a wake-up with only a hash of the topic name, never the
message. The app wakes up and fetches the message from your own server.

On the phone, set the notification channel for `urgent` to override Do Not Disturb, or a `CRITICAL`
alert stays silent at night. Give the alerts topic its own sound.

### Home Assistant and uptime monitoring

Home Assistant needs no integration: a REST sensor on
`/api/events?level=ERROR&level=CRITICAL&since=-1h`, with the API key as a header, gives you the
event count. `GET /health` returns HTTP 503 (`"status": "degraded"`) when the database is
unreachable or a background thread has stopped, so an uptime monitor on that endpoint tells you
when something is wrong.

## CI

The pipeline is GitLab CI (`.gitlab-ci.yml`) on the maintainer's GitLab, so it does not run on this
mirror. Every job calls a script you can run locally, for example
`./scripts/test/music-management-unit.sh` for the Python unit tests or
`./scripts/test/frontend-unit.sh` for the web player. [CONTRIBUTING.md](CONTRIBUTING.md) lists them
with the formatters, linters and type checks.

The branch model is `feature/*` to `develop` to `release/x.y.z` to `master`. A merge request runs
only the checks for the parts it changes. `develop` adds the full-stack contract and browser tests.
A `release/*` branch builds and publishes the Docker images and the signed Android app. A merge to
`master` tags the release as `release-vX.Y.Z`, and an installation deploys from that tag
([docs/designs/ops-split/](docs/designs/ops-split/functional.md)).

## Source code and license

MuMa is licensed under the GNU AGPL-3.0 ([LICENSE](LICENSE)), except for two parts that come from other
projects and keep their GPL-3.0 licence. `services/music-management-server` is a fork of
[LMS](https://github.com/epoupon/lms) by Emeric Poupon (licence text in its `COPYING`).
`services/muma-mobile` derives from [Ultrasonic](https://gitlab.com/ultrasonic/ultrasonic) (licence text in
its `LICENSE`). [NOTICE](NOTICE) lists the parts with their copyright lines. Section 13 says that anyone who uses a
modified version over a network can get its source code. The About screen (Settings > About) of the
web player and of the Android app, which shows the same screen, has a **Source code** section with a
link for that, and the login screen has the same link, so it reaches people before they sign in.

The link comes from the setting `public_source_url` (environment variable `PUBLIC_SOURCE_URL`, also on
Management > Configuration > General). The default is the placeholder `https://github.com/OWNER/music-management`.
If you run your own fork, set it to the address of your repository, at the revision you deploy. An
empty value hides the section. Only `http://` and `https://` addresses are shown. The About screen
reads the value from `source_url` in the `GET /health` answer.

The music server (`services/music-management-server`) is a fork of LMS and has its own, older Wt
interface with an About window that links to the upstream LMS homepage. The web player is the interface
this project serves to listeners, so the source link lives there.

## Repository structure

```text
├── services/                    # System components
│   ├── frontend/                # Svelte web player and Management pages
│   ├── music_manager/           # Management API, ratings, listens, BPM analyzer
│   ├── music-management-server/ # Streaming server and Subsonic API (LMS fork)
│   ├── downloader/              # YouTube, SoundCloud and Telegram workers
│   ├── importer/                # Archive extraction and placement
│   ├── tagger/                  # Rule-based tagging engine
│   ├── scanner/                 # Library scan and sync
│   ├── muma-mobile/             # Android app
│   ├── ml-analyzer/             # Deprecated
│   └── common/                  # Shared code
├── docs/                        # Designs, bug reports and guides
├── scripts/                     # Build, test and CI scripts
└── tools/                       # One-off maintenance scripts
```

## Documentation

- [Product goal](docs/product-goal.md): what the system is for, and what it is not
- [Architecture](docs/architecture.md): services, data flow and data ownership
- [API specification](docs/api-specification.md)
- [Self-hosting](docs/self-hosting.md)
- [Testing inventory](docs/testing-inventory.md)
- [Database schema](docs/database-design.md)
- [Style guide](docs/styleguide.md)
- [Contributing](CONTRIBUTING.md) and [security](SECURITY.md)
