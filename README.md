# 🎵 Music Management System

[![license](https://img.shields.io/badge/license-AGPL--3.0-blue)](LICENSE)

A comprehensive, modular system for automated music library management, featuring a unified "Spotify-style" UI, automated downloading, rule-based tagging, ML analysis, and Subsonic-compatible playback.

## 🧩 Modular System Architecture

The project is built as a set of specialized services that work together to manage the full music lifecycle.

### Core Services
- **`frontend`**: A unified Svelte-based "Spotify UI" that handles both playback and system management.
- **`music-manager`**: The central hub and "Source of Truth". Manages metadata, ratings, scrobbling, and coordinates background tasks.
- **`music-management-server`**: The high-performance C++ playback engine. Provides audio streaming and the Subsonic API.

### Specialized Workers
- **`muma-scanner`**: High-performance library scanning and database synchronization.
- **`muma-tagger`**: Rule-based metadata enforcement and genre inference engine.
- **`muma-downloader`**: Automated fetches from YouTube and SoundCloud.
- **`muma-telegram`**: Dedicated worker for Telegram-based music discovery.
- **`muma-importer`**: Archive extraction and automated file movement.
- **`muma-ml-analyzer`**: Machine learning pipeline for BPM, key, and mood detection.

---

## 🏗 Project Modules

### 1. Unified Frontend (`services/frontend`)
A modern, responsive Svelte application that provides:
- **Playback Control**: Integrated player with queue management.
- **System Management**: Dedicated "Systeembeheer" (System Management) dashboard for Tagger, Scanner, User management, and Worker status.
- **Library View**: Rich browsing by artist, album, and genre.

### 2. Music Manager (`services/music_manager`)
A FastAPI service acting as the management backend:
- Consolidates ratings, scrobbling history, and stats.
- Manages the "Artist Image Fetcher" for metadata enrichment.
- Keeps a severity-tagged event log (`/api/events`) as the source of truth; `ntfy.sh` is a downstream push sink, not the origin of the data.

### 3. Music Management Server (`services/music-management-server`)
The core streaming component:
- Provides a stable Subsonic-compatible API for mobile apps like MuMa Mobile.
- Handles high-performance audio streaming.
- Integrated directly into the management ecosystem.

### 4. Mobile Client: MuMa Mobile
The ecosystem includes a dedicated mobile experience via the **MuMa Mobile** Android app:
- **Subsonic API**: Connects to the Music Management Server for streaming.
- **Settings Sync**: Automatically synchronizes application settings (themes, bookmarks, player preferences) to the Music Manager API.
- **Rating Integration**: Ratings changed in the app are propagated back to the central database.
- **Distribution**: The app is a normal APK. Hand it out any way you like, for example GitHub Releases or sideloading.

---

## 🚀 Getting Started

The easiest way to run the entire stack is using Docker Compose.

### Prerequisites
- Docker and Docker Compose
- Current user in the `docker` group (for building images)
- Docker Hub account and `docker login` (if pushing images to the registry)
- `sshpass` (optional, for automated remote deployment)
- A MariaDB/MySQL database (included in compose)

### Quick Start
1. Clone the repository.
2. Copy `.env.example` to `.env` and fill in your paths, database credentials and keys.
3. Build the images on the host with `./build.sh --skip-lint --skip-test`.
4. Start the stack with `docker-compose -f docker/docker-compose.yml --env-file .env up -d`.

`install.sh` does not install Docker and does not create `.env`. It builds, publishes to Docker Hub
and deploys over SSH, so it is for maintainers. [docs/self-hosting.md](docs/self-hosting.md) has the
full steps: the keys, the source worker profiles, the player stack and the nginx file.

### Building and Deployment
If you are modifying the code and need to rebuild and redeploy the system:

- **Full pipeline (Build + Publish + Deploy)**: `./install.sh`
  - Uses `scripts/affected.sh` to detect which modules have changed if no modules are specified.
  - Skips builds and pushes for unedited modules to save time.
  - Automatically deploys the updated stack to production.
  - **New**: Use `--semi-remote` to offload heavy builds (`app`, `ml`, `tools`) to a remote build host.
  - **New**: Use `--remote` to perform the entire build on a remote build host.
  - **New**: Use `--app=<app>` or positional arguments to target specific modules (e.g., `./install.sh --app=user rating`).
  - **New**: Use `./install.sh manager` to view music library statistics from the terminal.
- **Individual steps**:
  - Build: `./build.sh`
  - Publish: `./publish.sh`
  - Deploy: `./deploy.sh`

#### Remote Deployment Options
You can configure deployment in `.env`:
1. **Portainer Webhook**: Set `PORTAINER_WEBHOOK_URL`.
   - **Business Edition**: Supports "Stack Webhooks" (triggers a full stack redeploy).
   - **Community Edition**: Supports "Service Webhooks" (trigger per service). If you have multiple services, you might prefer the SSH method.
2. **SSH**: Set `REMOTE_HOST`, `REMOTE_USER`, etc. The script will automatically discover your Docker Compose configuration (even if managed by Portainer), transfer it securely, and redeploy the stack. If the stack does not exist yet, it will be created using the local `docker-compose.yml` template. This method is highly recommended for multi-host setups and Community Edition users.

**Tip**: Use `DEPLOY_TARGET_NAME` in `.env` to give your deployment target a friendly name (e.g., "Production Stack"). The system now uses this to automatically manage stack naming and discovery across different repositories.

You can also target specific components with `build.sh` and `publish.sh`:
- `./build.sh ml` (ML Analyzer only)
- `./build.sh tools` (Tools only)
- `./build.sh app` (Main Application only)

The following services will be available:
- **Music Management Server (Spotify UI)**: Port 5082
- **Music Manager (API)**: Port 8000
- **phpMyAdmin**: Port 8002 (to inspect the database)

### User Management

You can manage users via the Systeembeheer dashboard in the frontend. 
If you need to set or reset a user's password via the command line, use the provided script:

```bash
./scripts/set_user_password.sh <username>
```

The script will prompt you for a password and confirmation. You can also provide the password directly with `--password <pass>`, but this is less secure as it might be stored in your shell history.

---

## 🛠 Docker Stack Management

The system is split into modular Docker Compose files for better resource management:

1. **`docker/docker-compose.yml`**: What production runs (`scripts/ci-deploy.sh`): MariaDB, phpMyAdmin,
   Music Manager (which hosts the tagger and scanner) and the importer, YouTube, SoundCloud and
   Telegram workers. LMS is its own stack (`services/music-management-server/docker-compose.yml`).
2. **`docker/docker-compose.workers.yml`**: Local-only overlay used by `scripts/dev.sh` (which also reads the optional, gitignored `.production` file of the owner's checkout for `DOCKER_USER`). It redefines
   the same worker containers with a flat, older environment and is not valid on its own (its
   workers depend on a `db` only `docker-compose.yml` defines). Production never reads it.
3. **`docker-compose.tools.yml`**: Utility services (Fetchers, ML Analyzer, Firefox).

#### Source workers are opt-in

The workers that bring music into the library are Compose profiles. Without a profile, `up` starts
the database, the manager and the other core services, and none of them:

| Profile      | Services                            | For                                                                  |
|--------------|-------------------------------------|----------------------------------------------------------------------|
| `importer`   | `importer_worker`                   | Music you bought or got as a label promo, placed into your library.  |
| `soundcloud` | `soundcloud_worker`, `soundcloud-fetcher` | Tracks an artist or label published on their own SoundCloud channel. |
| `youtube`    | `youtube_worker`                    | Tracks an artist or label published on their own YouTube channel.    |
| `telegram`   | `telegram_worker`                   | Files from Telegram chats you take part in.                          |

Turn them on with `COMPOSE_PROFILES` in `.env`, for example `COMPOSE_PROFILES=importer,youtube`, or per
command with `docker-compose --profile importer up -d`. See
[docs/self-hosting.md](docs/self-hosting.md#source-workers-are-compose-profiles).

### Database Backups
A SQL dump of the MariaDB database is automatically created during every deployment. Manual backups can be triggered using:
```bash
./tools/backup_db.sh
```
Backups are stored in `/muma/backups` on the host machine. The script uses `docker exec` to perform the dump within the running database container.

### Common Commands:

**Start the entire stack:**
```bash
docker-compose -f docker/docker-compose.yml -f docker/docker-compose.tools.yml \
  --profile importer --profile soundcloud --profile youtube --profile telegram up -d
```
(or `COMPOSE_PROFILES=importer,soundcloud,youtube,telegram` in `.env`, then a plain `up -d`)

**Start only core services (no source workers):**
```bash
docker-compose -f docker/docker-compose.yml up -d
```

**View logs for a specific service:**
```bash
docker-compose -f docker/docker-compose.yml --profile importer logs -f importer_worker
```

---

## 🔔 Event Log & Alerts

Every service writes structured events (`INFO`/`WARNING`/`ERROR`/`CRITICAL`) straight to the `events`
table via `EventService`; that table is the source of truth, browsable in the frontend's Logboek tab
and queryable via `GET /api/events` (see [API Specification](docs/api-specification.md)). `ntfy.sh` is
a downstream sink, not the origin: the database keeps every event even if ntfy is unreachable. Two
topics exist so milestones and alerts can have their own sound and visibility:
- `notify_topic` (default `music-management`) — download/import milestones, pushed only when the
  emitting code explicitly opts in.
- `notify_topic_alerts` (default `music-management-alerts`) — every `WARNING` and higher,
  automatically, with `Priority: high` (`WARNING`/`ERROR`) or `urgent` (`CRITICAL`). A repeat from
  the same level/source/logger within five minutes is still written to the database but not pushed
  again, so a warning that repeats every sweep cannot flood the phone.

Filtering by source offers three values — `music-manager`, `downloader` and `importer` — the three
processes that set up their own logging. The tagger and scanner loops are threads inside
music-manager, so their events appear under `music-manager`.

### Deployment prerequisite: instant delivery on a self-hosted ntfy server
The official ntfy Android app uses Firebase for instant push, but only for topics hosted on
`ntfy.sh` itself. Against a self-hosted server (this project uses `ntfy.example.com`) the app
falls back to periodic polling, so a `CRITICAL` alert can arrive minutes late — which defeats the
point of the alerts topic. The fix lives outside this repository, in the ntfy server's `server.yml`:

```yaml
upstream-base-url: "https://ntfy.sh"
```

With that line set, the self-hosted server sends a wake-up to `ntfy.sh` containing only a hash of
the topic name — never the title or message body. `ntfy.sh` fires a Firebase push, the app wakes up
and fetches the real message from the self-hosted server. Delivery is then instant, costs no extra
battery, and the actual content never leaves the home network. Without this line the feature works
exactly as designed, just late.

### One-off device setup
- The ntfy app creates a separate Android notification channel per priority. The channel used for
  `urgent` (i.e. `CRITICAL`) must be set to override Do Not Disturb, or a `CRITICAL` alert stays
  silent at night.
- Give the alerts topic its own notification sound, distinct from the milestones topic, so a
  `CRITICAL` is recognizable without looking at the phone.

### Home Assistant and uptime monitoring
Home Assistant needs no dedicated integration: a REST sensor polling
`/api/events?level=ERROR&level=CRITICAL&since=-1h` with the API key as a header is enough to drive
automations off the event count. Separately, `GET /health` now returns HTTP 503 (with
`"status": "degraded"`) when the database is unreachable or a background thread has died, instead of
always answering `ok` — this is what makes the existing Uptime Kuma monitor on that endpoint
meaningful; no change is needed on the Kuma side.

---

## 🔁 CI/CD Pipelines

Everything is driven by one GitLab pipeline definition (`.gitlab-ci.yml`), but *which* jobs
actually run depends entirely on the branch you push to. There are effectively four kinds of
pipeline, matching the branch model `feature/*` → `develop` → `release/x.y.z` → `master`.

### The four pipelines at a glance

| Pipeline | Triggered by | What it does | Touches production? |
| --- | --- | --- | --- |
| **Feature / merge request** | a push to `feature/*` or any branch with an open MR | Only the tests for the parts you actually changed. Fast feedback while reviewing. | No |
| **Integration (`develop`)** | a push/merge to `develop` | The changed-code tests *plus* the full stack tests (contract + browser), which always run here. This is the "does everything still fit together" gate. | No |
| **Release (`release/x.y.z`)** | creating/pushing a release branch | Checks the release paperwork and secrets, builds and publishes all Docker images and the signed Android app. | No |
| **Production record (`master`)** | merging a release branch to `master` | No tests. Checks that the release was published, tags it and merges `master` back into `develop`. The tag starts the deploy of an installation that watches it. | Through the tag |

### Which job runs when

Every job is named `<scope>:<what>`. The scope is the **source component** — the thing you
edited, which is also what the `changes:` rules key on:

| Scope | Is |
| --- | --- |
| `backend` | the Python tree: music-manager, importer, downloader, tagger, scanner, tools |
| `server` | the C++ playback server |
| `frontend` | the Svelte web UI (built into the server's image, not deployed separately) |
| `mobile` | the Android app |
| `muma` | spans components, or is the whole product: contracts, e2e, images |
| `security`, `deps`, `runner`, `release` | concerns that belong to no component |

Every component answers the same three questions — **format**, **lint**, **unit** — plus
extras where they genuinely exist (`backend:typecheck`, `mobile:smoke`). A policy test
enforces both halves of the name, and fails if a component is missing one of the three.

`backend` and `server` are both server-side: `server` is the C++ playback server,
`backend` is everything Python. The toolchains tell them apart at a glance —
`server:format` is clang-format, `backend:format` is ruff.

**Test jobs** — these only start when something they care about actually changed, so an
MuMa Mobile-only change doesn't wait on the C++ or frontend suites:

| Job | Runs when | Purpose |
| --- | --- | --- |
| `backend:format` / `:lint` / `:typecheck` | the Python services changed | ruff format, ruff + pylint, mypy. Fix formatting with `./scripts/format.sh`. |
| `backend:unit` | the Python services changed | Unit tests for music-manager, importer, downloader, tagger, scanner and shared code. Reports coverage. |
| `backend:integration` | the manager's SQL, the schema declaration or the integration suite changed | Runs every endpoint's SQL against a real MariaDB. |
| `server:format` | the server sources changed | clang-format check, pinned to one clang version. Fix with `./scripts/test/muma-server-format.sh --fix`. |
| `server:lint` | the server sources changed | clang-tidy over 307 translation units against a baseline of accepted findings. ~12 minutes, so it is deliberately not on every pipeline. |
| `server:unit` | the playback server (C++) changed | Builds and runs the LMS test suite. Reports coverage. |
| `frontend:format` / `:lint` / `:typecheck` | the Svelte frontend changed | oxfmt, oxlint + eslint (a warning fails the job), svelte-check. |
| `frontend:unit` | the Svelte frontend changed | Vitest with coverage. |
| `mobile:format` | the Android app changed | ktlint. Fix with `./scripts/test/muma-mobile-ktlint.sh ktlintFormat`. |
| `mobile:lint` | the Android app changed | detekt (no baseline: every finding fails) and Android Lint (against a baseline). |
| `mobile:unit` | the Android app changed | MuMa Mobile unit tests with coverage. |
| `muma:contracts` | always on `develop`; elsewhere only if the server, music-manager or the test stack changed | Starts the real test stack and verifies the Subsonic/OpenSubsonic API still behaves as the mobile clients expect. |
| `frontend:e2e` | always on `develop`; elsewhere only if the frontend or test stack changed | Real browser (Playwright) run against a live stack: import a track, scan it, click through the UI. Screenshots/traces are kept for 14 days. |

**Release jobs** — these only exist on a `release/*` branch, and they run in order so the
pipeline fails as early and as cheaply as possible:

| Job | Purpose |
| --- | --- |
| `release:check-secrets` | Runs first, before anything is built: refuses to continue if a deployment secret needed by production is missing or empty. A release pipeline that skips this job is not considered green. |
| `release:version-check` | Enforces that the release was actually prepared: `VERSION` bumped, a dated `CHANGELOG.md` entry, release notes updated, and an MuMa Mobile version bump if the app changed. |
| `release:build-images` | Builds and pushes every Docker image production pulls, so the deploy can never pick up a stale, manually pushed image. |
| `mobile:build-release` | Builds the signed Android release APK and publishes it to this project's package registry (`muma-mobile/<versionName>`). Waits for `release:version-check`. |

Nothing here deploys. An installation deploys a release from its tag (see
[docs/designs/ops-split/](docs/designs/ops-split/functional.md)).

**Post-release jobs** — these run on `master` after the release branch is merged:

| Job | Purpose |
| --- | --- |
| `release:publish` | Checks that the release branch pipeline built the images and the APK package for the merged commit. A release whose build was skipped or cancelled stops here, untagged. |
| `release:tag` | Creates the immutable `release-vX.Y.Z` tag (and `muma-mobile-vX.Y.Z` when the app was part of the release), after `release:publish`. Tags are never made by hand. The tag is what an installation deploys. |
| `release:back-merge-develop` | Merges `master` back into `develop` automatically and deletes the merged release branch, so `develop` never drifts and stale release branches can't redeploy old code later. |

### Handy extras

- **Debug APK on demand**: `mobile:build-debug` runs automatically on `develop` when the app
  changed, and is available as a *manual* button on any other branch — useful for handing a
  reviewer a test build of a UI fix before merging.
- **Interruptible by default**: pushing again cancels the previous run of the same branch, except
  for the release gates, the image build, the APK publish and the tagging/back-merge jobs, which are
  never interrupted halfway.
- **Self-healing runner**: before checkout, the pipeline reclaims any files the Android build left
  behind as root, so a crashed runner doesn't wedge every later pipeline.

---

## Source code and license

MuMa is licensed under the GNU AGPL-3.0 ([LICENSE](LICENSE)). Section 13 says that anyone who uses a
modified version over a network can get its source code. The About screen (Settings > About) of the
web player and of the Android app, which shows the same screen, has a **Source code** section with a
link for that, and the login screen has the same link, so it reaches people before they sign in.

The link comes from the setting `public_source_url` (environment variable `PUBLIC_SOURCE_URL`, also on
Beheer > Config > General). The default is the placeholder `https://github.com/OWNER/music-management`.
If you run your own fork, set it to the address of your repository, at the revision you deploy. An
empty value hides the section. Only `http://` and `https://` addresses are shown. The About screen
reads the value from `source_url` in the `GET /health` answer.

The music server (`services/music-management-server`) is a fork of LMS and has its own, older Wt
interface with an About window that links to the upstream LMS homepage. The web player is the interface
this project serves to listeners, so the source link lives there.

## 📂 Repository Structure

```text
├── services/               # System components
│   ├── frontend/           # Unified Svelte UI (Spotify UI + Management)
│   ├── music_manager/      # Management API, Ratings, Scrobbling
│   ├── music-management-server/ # Playback Engine & Subsonic API
│   ├── downloader/         # YouTube, SoundCloud, Telegram workers
│   ├── importer/           # File movement and extraction
│   ├── tagger/             # Rule-based tagging engine
│   ├── ml-analyzer/        # ML audio feature extraction
│   ├── scanner/            # Library scan and sync
│   ├── muma-mobile/        # Android mobile client
│   └── common/             # Shared logic and internal API
├── docs/                   # Detailed documentation and diagrams
└── tools/                  # Utility scripts
```

---

## 📖 Detailed Documentation

For specific information on each module, please refer to their respective READMEs:

- [Product Goal](docs/product-goal.md) — what the system is for, and what it deliberately is not
- [Architecture](docs/architecture.md) — services, data flow and data ownership
- [API Specification](docs/api-specification.md)
- [Self-Hosting Guide](docs/self-hosting.md)
- [Testing Inventory](docs/testing-inventory.md)
- [Database Schema](docs/database-design.md)
- [Style Guide](docs/styleguide.md)

---

## 👨‍💻 Development

This project is primarily designed for personal use, tailored to specific workflows for electronic music (Hardcore, Hardstyle, etc.).

### Tools
Check the `tools/` directory for utility scripts like `process_genres.py`.

### Testing
Run tests using pytest:
```bash
pytest
```
