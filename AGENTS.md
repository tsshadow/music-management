# 🤖 Agent Information & System Workflow

This document provides a high-level overview of the Music Management System's internal logic, module interactions, and integrations for AI agents and developers.

## 📦 Repository Layout

This is a single monorepo containing every application in the ecosystem: the Python backend services, the
C++ `music-management-server` (LMS fork), the Svelte `frontend`, and the `muma-mobile` Android app all live
directly under `services/`, with one shared Git history. There are no submodules and no separate, split-out
repositories — a change that touches multiple apps (e.g. a new rating feature spanning the backend, the web
player and the Android client) is made and committed as a single, atomic change here. Each part still has
its own independent build/deploy pipeline (see `build.sh`, `docker/`, and each service's own `scripts/`), only
the source code and history are shared.

## 🏗 Core Modules & Responsibilities

The system is split into specialized services, each handling a specific part of the music lifecycle:

### 1. `downloader` (`services/downloader`)
- **Sources**: SoundCloud, YouTube, and Telegram.
- **Technology**: Uses `yt-dlp` for SoundCloud/YouTube and a custom Telegram implementation.
- **Logic**: Downloads tracks, extracts metadata (uploader, title, tags), and passes them to the `tagger` for normalization.
- **Service**: Managed via `downloader_service.py` with different `--step` flags for each source.

### 2. `importer` (`services/importer`)
- **Purpose**: Processes incoming music from external sources (e.g., label promo pools, manual downloads).
- **Functionality**:
    - **Extraction**: Unpacks `.zip` and `.rar` archives.
    - **Metadata Extraction**: Infers Publisher and Catalog Number from the folder structure (e.g., `/Labels/Scantraxx/SCAN123/`).
    - **Tagging**: Uses `LabelSong` to apply rule-based metadata.
- **Workflow**: `Monitor` -> `Extract` -> `Tag` -> `Move` to the final library destination.

### 3. `tagger` (Integrated in `music-manager`)
- **Engine**: The core metadata enforcement system.
- **Features**:
    - **Auto-Detection**: `TagSingleFile(path)` automatically detects the song type (SoundCloud, YouTube, Label, etc.) based on its file location and applies appropriate tagging rules.
    - **REST API**: Integrated into `music-manager` (Port 8000) under `/api/tagger`:
        - `POST /api/tagger/tag/all`: Runs the full tagging pipeline in background.
        - `POST /api/tagger/tag/file?path=...`: Tags a single file with auto-detection.
        - `GET /api/tagger/health`: Health check and status.
- **Song Types**:
    - `SoundcloudSong`: Specialized in SoundCloud metadata (e.g., handling "Premiere" prefixes).
    - `YoutubeSong`: Runs the same rule stack as `SoundcloudSong` — the artists usually only exist in the title, whether the channel belongs to the artist or to a label. What differs is the album (`Youtube (<channel>)`), the publisher, the festival inference, and the channel-to-genre lookup.
    - `LabelSong`: Mapping folder structures to Publisher/Catalog tags and copyright strings.
- **Rules**: A flexible rule engine (`services/tagger/Song/rules/`) that handles:
    - Genre inference based on artists or subgenres.
    - Artist normalization (casing, splitting featured artists).
    - Remixer extraction from titles and assignment to `REMIXER` tag.
    - Cleanup of invalid characters (e.g., zero-width spaces).
- **Background Task**: Managed via a background thread in `music-manager`.

### 4. `scanner` (Integrated in `music-manager`)
- **Role**: Synchronizes the filesystem with the database.
- **Features**:
    - **Metadata Extraction**: Reads tags from audio files and updates the `library_tracks`, `library_artists`, etc., tables.
    - **REST API**: Integrated into `music-manager` (Port 8000) under `/api/scanner`:
        - `POST /api/scanner/scan/all`: Runs a full library scan in background.
        - `POST /api/scanner/scan/file?path=...`: Scans a single file and updates its database record.
        - `GET /api/scanner/health`: Health check and status.
    - **Redownload Service**: Allows triggering redownloads for tracks that originated from SoundCloud or YouTube.
        - Automatically matches library tracks to original source URLs using the download archive.
        - `POST /api/library/tracks/{id}/redownload`: Starts a background redownload task.

### 5. `music-management-server` (`services/music-management-server`)
- **Role**: The high-performance playback and streaming engine.
- **Backend**: C++/SQLite based server providing audio streaming and Subsonic API.
- **Data Scope**: Maintains a volatile database (`lms.db`) for indexing local files and managing playback state.
- **UI**: Unified Svelte-based "Spotify UI" that includes both playback and system management.

### 6. `music-manager` (`services/music_manager`)
- **Role**: The "Source of Truth" and central hub for long-term library maintenance and management logic.
- **Backend**: FastAPI service managing:
    - User authentication (synchronizing with `music-management-server`).
    - Permanent track ratings and consolidated scrobbling history.
    - Master copies of metadata rules (genres, labels, artist normalization).
    - The severity-tagged event log (`events` table, `/api/events`); `ntfy.sh` is a downstream push
      sink, not the source of truth — see [Events & Alerts](#-events--alerts) below.
    - Dashboard API for the Svelte frontend.
    - **Integrated Services**: Hosts the `tagger` and `scanner` logic to enforce library standards.
- **See Also**: [docs/architecture/responsibilities.md](docs/architecture/responsibilities.md) for data boundary details.

### 5. `ml-analyzer` (`services/ml-analyzer`)
- **Purpose**: Audio analysis for advanced metadata.
- **Features**: Detects BPM, Musical Key, and Mood using machine learning models.

---

## 🔄 System Workflow

1. **Ingestion**: A new track enters via `downloader`, `importer`, or `telegram`.
2. **Standardization**: The `tagger` service applies site-specific or label-specific rules to ensure metadata consistency.
3. **Database Update**: Metadata and tracking information are saved to the MariaDB `music_management` database.
4. **Library Placement**: The file is moved to its permanent location in the music library.
5. **Server Sync**: Music Management Server rescans the library, making the music available for playback.
6. **Notification**: An `INFO` event with `push=True` is emitted, its message formatted via
   `BaseSong.__str__`. It is written to the event log and, because push was requested, also relayed
   to the user's mobile device via ntfy.

---

## 🔔 Events & Alerts

Every service writes structured events (`INFO`/`WARNING`/`ERROR`/`CRITICAL`) directly to the `events`
table through `EventService`; that table is the source of truth, not `ntfy.sh`. Each event then fans
out to every registered sink, of which ntfy is currently the only one — so an event still exists,
queryable via `GET /api/events`, even if ntfy itself is unreachable. This is the reverse of the
pre-events design, where code POSTed to ntfy and a listener thread read it back to populate the
database.

Two ntfy topics keep milestones and alerts separate, since the ntfy Android app subscribes per topic
and does not filter reliably on priority:
- `notify_topic` (default `music-management`) — download/import milestones. Reached only when the
  emitting code passes `push=True` (four call sites today).
- `notify_topic_alerts` (default `music-management-alerts`) — every `WARNING` and higher,
  automatically, with `Priority: high` (`WARNING`/`ERROR`) or `urgent` (`CRITICAL`) and a
  severity-specific tag. A repeat of `(level, source, logger)` within a 5-minute window produces a
  database row but no repeat push, so a single flapping connection cannot flood the phone. The key
  deliberately ignores the title: routine warnings embed a changing countdown in their text
  (`"still cooling down for 240s"`), and keying on the title would mean the brake never engages.
  Events emitted directly, without a logger name, fall back to the title.

`setup_logging(source)` decides what reaches the stream: `ALLOWED_PREFIXES` (`music-manager`,
`downloader`, `importer`, `tagger`, `scanner`, `root` and their subloggers) is captured from `INFO`
upward, everything else — uvicorn's access log above all — only from `WARNING`. `root` is on that
list because the worker services log through the module-level API (`logging.info(...)`) rather than
a named logger, so their records arrive as `root`; without it every `INFO` from the downloader and
importer was dropped. The `source` field still identifies the process, since `setup_logging` sets it
per service — only the `logger` column is uninformative for those rows. Filtering `/api/events` by
source therefore offers exactly three values: `music-manager`, `downloader`, `importer`. The tagger
and scanner loops run as threads inside the music-manager process and emit under its source.

### Deployment prerequisite: `upstream-base-url`
Instant delivery on the phone depends on a setting outside this repository. The official ntfy
Android app uses Firebase for push, but only for topics hosted on `ntfy.sh` itself; against a
self-hosted server (`ntfy.example.com` here) the app falls back to periodic polling, so a
`CRITICAL` could arrive minutes late — defeating the purpose of the alerts topic. The fix is one line
in the self-hosted server's `server.yml`:

```yaml
upstream-base-url: "https://ntfy.sh"
```

With that line set, the self-hosted server sends `ntfy.sh` a wake-up containing only a hash of the
topic name (never the title or message body); `ntfy.sh` fires the Firebase push, and the app fetches
the real message from the self-hosted server. Delivery is instant, costs no extra battery, and
content never leaves the home network. Without it, the code-side implementation is unaffected —
alerts just arrive late.

Two one-off steps on the device itself: the ntfy app creates a separate Android notification channel
per priority, so the channel backing `urgent` (i.e. `CRITICAL`) must be set to override Do Not
Disturb, or a `CRITICAL` stays silent at night; and the alerts topic should get its own notification
sound, distinct from the milestones topic.

### Home Assistant and health monitoring
Home Assistant needs no dedicated integration — a REST sensor on
`/api/events?level=ERROR&level=CRITICAL&since=-1h`, with the API key sent as a header, is enough to
drive automations off the event count. Separately, `GET /health` reports `status`, `service`,
`version`, `database` (`ok`/`unreachable`) and `threads` (the long-running loops: `tagger`,
`scanner`, `radio`, `events-retention`, plus `events` for the event worker), and returns HTTP 503
when any of those is unhealthy — instead of the old hard-coded `ok`. This is what makes the existing
Uptime Kuma monitor on that endpoint meaningful; nothing needs to change on the Kuma side.

---

## 🔗 Integrations

These apps live in this same monorepo (see [Repository Layout](#-repository-layout) above) but are still
separately built/deployed, and talk to each other only over HTTP/Subsonic APIs:

### Music Management Server
- **Playback Engine**: The primary server for audio streaming and library management.
- **Data Sync**:
    - `music-manager` directly mounts and interacts with the Server database (SQLite) to synchronize users and permissions.
    - Synchronizes song ratings bidirectionally between the local database and the Server.
    - Uses the Subsonic API provided by the Server for client authentication and playback.

### MuMa Mobile (`services/muma-mobile`)
- **Mobile Client**: A native Android application for interacting with the music collection on the go.
- **Subsonic Integration**: Connects directly to the `music-management-server` for audio streaming and library browsing.
- **Settings Backup & Sync**:
    - Synchronizes application settings (stored as JSON) to the `music-manager` API (`POST /api/users/{id}/app-settings/ultrasonic`).
    - Provides a seamless transition when switching devices or re-installing the app.
- **Real-time Feedback**:
    - **Ratings**: Star ratings changed within MuMa Mobile are sent to LMS via the Subsonic API and then webhooked to `music-manager`.
    - **Scrobbles**: Playback history is reported via LMS to the central scrobbling engine.
- **Distribution**: Updates are managed via a dedicated `apk-hoster` service, allowing for independent delivery outside of app stores.

---

## 🧪 Testing & Stability

To maintain high code quality, the system employs an automated test suite:
- **Location**: `services/downloader/*/tests/` and `services/importer/tests/`.
- **Mocking**: Uses a unified `mock_base.py` to provide an isolated environment (mocking `mutagen`, `yt-dlp`, and database helpers).
- **Enforcement**: 
    - **Build Check**: `build.sh` executes the full test suite and aborts the container build if any tests fail.
    - **Pre-commit Hook**: A Git `pre-commit` hook ensures all tests pass before allowing a commit to be finalized.
    - **Required deployment secrets**: the `release:check-secrets` CI job (`scripts/ci/check-required-secrets.sh`)
      verifies that specific keys required inside file-type CI/CD variables (e.g. `GOOGLE_CLIENT_ID` inside
      `PROD_ENV_FILE`, `VITE_GOOGLE_CLIENT_ID` inside `PROD_ENV_FILE_LMS`) are actually set, and fails the
      `release/*` pipeline immediately if not. GitLab itself has no mechanism to enforce this (a file-type
      variable being non-empty says nothing about a specific key inside it), so **this job's pass/fail result
      is treated as a hard requirement by project convention, on par with any other required check in this
      list** — a release is not "done" if this job was skipped, allowed to fail, or removed without a
      replacement check covering the same secrets. Add new required keys to that script (and to
      `docs/deployment.md`) whenever a new secret becomes load-bearing for production.

### Full test inventory & local commands
- **Inventory**: See [docs/testing-inventory.md](docs/testing-inventory.md) for a per-module breakdown (build/start/test/lint commands, ports, health endpoints, databases, Docker findings).
- **Quality gates** — all enforced in CI (`quality` stage) and by the versioned pre-commit
  hook (`./scripts/install-hooks.sh`), which is a thin wrapper around the same scripts so the
  two cannot drift:
    - `./scripts/lint.sh` — ruff (config in `pyproject.toml`) + pylint, threshold 9.5.
    - `./scripts/typecheck.sh` — mypy. Rolled out per module: `pyproject.toml` holds a loose
      floor for the whole tree and lists the strictly-checked modules. That list only grows.
    - `./scripts/format.sh <path>` — opt-in `ruff format`. Deliberately not in CI: a tree-wide
      reformat would rewrite nearly every file and conflict with every open branch.
    - `./scripts/ci/dependency-audit.sh` — pip-audit + npm audit. Runs on a schedule and on the
      default branch, not as a merge-request gate (it audits the runner's environment, which
      this repository does not manage). Accepted findings, with a reason, live in
      `security/accepted-vulnerabilities.txt`.
- **Ratchets** — `FAIL_UNDER` in `scripts/lint.sh` (9.5), `COVERAGE_MIN` in
  `scripts/test/music-management-unit.sh` (85%) and the `thresholds` in
  `services/frontend/vite.config.js` are floors. Raise them as the numbers climb; never lower
  one to make a red build green.
- **Uniform local test scripts** (`scripts/test/`), run the same way locally and in CI:
    - `./scripts/test/music-management-unit.sh` — Python unit tests, whole `services/` and
      `tools/` tree, with the coverage gate.
    - `./scripts/test/db-integration.sh` — every endpoint's SQL against a throwaway MariaDB,
      plus the schema bootstrap and every `migrate_*.sql` applied twice. The unit suite mocks
      the cursor, so this is the only thing that proves MariaDB accepts the queries.
    - `./scripts/test/muma-server-unit.sh` — LMS C++ unit tests (existing upstream CTest/GTest suite).
    - `./scripts/test/frontend-unit.sh` — frontend lint + svelte-check + vitest with coverage.
    - `./scripts/test/android-unit.sh` — MuMa Mobile JVM unit tests.
    - `./scripts/test/core-smoke.sh` — builds and starts `docker/compose.test.yml` from a clean state, waits for all healthchecks, then tears down.
    - `./scripts/test/contracts.sh` — LMS/OpenSubsonic contract tests + listen/scrobble flow, against the test stack + fixture track.
    - `./scripts/test/frontend-browser.sh` — Playwright browser tests (login, fixture track visible) against the test stack.
    - `./scripts/test/core-e2e.sh` — the server chain, as Gherkin under `tests/bdd/features/`: the scan-to-listen walk, the listen that matches nothing, the rating hop from LMS, genre curation, and access control. Gates every pipeline as `e2e:scan-to-listen`. 45s to 90s, almost all of it waiting for three containers to report healthy — that wait swings with how loaded the runner is, while the tests themselves are ~4s. Needs `pytest-bdd`, and falls back to the tooling container when it is missing, as the runners' Python is.
      - The feature files are the description; the step code is not. If they disagree the feature file is right and the code is the bug.
      - Most of the setup is other people's state. LMS has no users of its own, so an account is created in `music-manager` and synced across, a library declared and scanned. Every `migrate_*.sql` is applied, because that is what a deploy does and what seeds `rules_genres`. And the tagger runs before either index is built — it is the only thing that registers a genre for curation, and it rewrites the file, so indexing before it leaves LMS serving new bytes under an old size.
- **Test stack**: `docker/compose.test.yml` — temporary MariaDB, `music-manager` and `music-management-server`, all built from the current checkout, disposable volumes, healthchecks. Never mounts real music/library paths or production data.
- **Fixture track**: `tests/fixtures/music/ci-test-track-001.mp3` (generated tone, no commercial audio) with expected metadata documented in `tests/fixtures/expected/ci-test-track-001.json`.
- **A new endpoint that reads the database** belongs in `tests/integration/test_router_sql.py`
  as well as in a unit test. **A schema change needs three edits**: the `CREATE TABLE` in
  `services/common/db_init.py`, a re-runnable `migrate_*.sql` in the repository root (applied
  on every deploy by `scripts/deploy.sh`), and the expected-tables list in
  `tests/integration/test_schema.py`. `CREATE TABLE IF NOT EXISTS` never alters an existing
  table -- that is how `downloads_youtube_accounts.channel_id` and
  `library_track_ml_labels.updated_at` went missing until the integration suite caught them.
- **See [CONTRIBUTING.md](CONTRIBUTING.md)** for the full local setup and the conventions
  above in one place, and [SECURITY.md](SECURITY.md) for the auth model and what is scanned.

---

## 🚀 Running Locally

To run services locally with the same environment as in Docker, you can use the following targets:

### 1. Shell Script
Use `scripts/run_local.sh` to launch any service with the correct `PYTHONPATH` and environment variables:
```bash
./scripts/run_local.sh importer
./scripts/run_local.sh soundcloud
./scripts/run_local.sh youtube
```

### 2. PyCharm Run Configurations
Pre-configured "Run Configurations" are available in the `.run/` directory. These will appear automatically in your IDE:
- **Importer Worker**: Runs `importer_service.py` with repeat enabled.
- **SoundCloud Worker**: Runs `downloader_service.py` for SoundCloud.
- **YouTube Worker**: Runs `downloader_service.py` for YouTube.

These configurations automatically load environment variables from your `.env` file and set the correct `PYTHONPATH`.

### 3. Password Management
Use `scripts/set_user_password.sh` to change a user's password directly from the terminal:
```bash
./scripts/set_user_password.sh <username>
```

### 4. Log Files
Log files should me located in the log directory.
If for dome reason a log file is not saved at that location, and you are done with it, move it to the log directory
---

## 🔌 API Specification
The full API specification for the `music-manager` service can be found in [docs/api-specification.md](docs/api-specification.md).

---

## 📜 Development Guidelines

To ensure consistency and reliability, all contributions (human or AI agent) must follow these rules. Each
rule is phrased as a concrete, checkable statement — if a rule is ambiguous for the change you're making, or
a design doc doesn't cover the case you're facing, **ask a clarifying question instead of guessing** (see
rule 11).

1. **Tests required**: every new feature or bug fix includes corresponding tests in the relevant `tests/`
   directory (see [Testing & Stability](#-testing--stability) above); a change to backend/CLI logic without
   a test is not considered done.
2. **English-only repository**: all code, comments, docstrings, commit messages, and documentation are
   written in English, regardless of the language used when the change was requested.
3. **Documentation kept current**: update `AGENTS.md`, `README.md`, or the relevant `docs/` file in the same
   change whenever system behavior changes — outdated documentation is treated as a bug.
4. **Design-first for non-trivial features**: a new feature, or any change to an existing flow's behavior,
   gets a functional design (`docs/designs/<feature>/functional.md`) and a technical design
   (`docs/designs/<feature>/technical.md`) — using the templates in `docs/designs/_template/` — written and
   agreed before implementation starts. Trivial fixes (typo, config value, dependency bump) are exempt. See
   [docs/designs/README.md](docs/designs/README.md) for the process and
   [docs/designs/authentication/](docs/designs/authentication/) for a worked example.
5. **Every function/class/component has a description**: a docstring or comment stating its purpose — no
   undocumented public function, class, or Svelte component.
6. **Frontend is Svelte**: `services/frontend` and the LMS-bundled UI stay Svelte + Tailwind, following
   [docs/styleguide.md](docs/styleguide.md); no other frontend framework is introduced.
7. **Cross-app API changes are atomic**: a change to an API contract shared between apps (e.g.
   `music-manager` REST endpoints consumed by `frontend`, LMS's Subsonic/`muma` proxy, or MuMa Mobile) updates
   *all* consumers in the same commit — matches the existing monorepo/atomic-change convention described
   under [Repository Layout](#-repository-layout).
8. **No secrets, ever, in code, commits, or docs**: credentials, tokens, and keys are never committed or
   written into `AGENTS.md`/`docs/`; they live only in a gitignored `.env` or in password manager, referenced by
   name only. Treat `AGENTS.md` and everything under `docs/` as potentially public.
9. **Changelog required**: every functional change updates `CHANGELOG.md`/`RELEASE_NOTES.md` in the same
   change.
10. **API versioning / contract discipline**: a breaking change to a shared API (request/response shape,
    auth requirements) is called out explicitly in the technical design and the changelog, and is verified
    against [docs/testing-inventory.md](docs/testing-inventory.md)'s contract tests
    (`scripts/test/contracts.sh`) before it's considered complete.
11. **Ask, don't guess**: when a design doc doesn't cover a case, or a rule conflicts with a specific
    request, ask a clarifying question rather than silently choosing an interpretation.
12. **Living document**: this rule list is updated whenever the process changes — a stale rule is worse than
    no rule. If a single service's rules ever outgrow this root file, a nested `services/<name>/AGENTS.md`
    can be added later (none is needed today).
13. **Structured Bug Reports**: Every bug report is captured in a 2-step process using `docs/bug-reports/00#-<title>.md`, containing:
    - `# title`
    - `# status: reported/analysed/fixed`
    - `# reported problem`
    - `# Possible reason`
    - `# solution`
14. **Open work is written down**: anything decided-but-not-done, or done-but-not-verified, gets a
    line in [docs/open-work.md](docs/open-work.md) pointing at wherever the detail lives. A bug
    report describes a fix, so it cannot carry a plan; a merge request description disappears from
    the repository entirely. Delete the line when the work is done — a stale entry there is a bug,
    same as a stale design doc (rule 3).
15. **Style Guide Adherence & Workflow**: All UI updates and new components across both the Web frontend (`services/frontend`) and the Android client (`services/muma-mobile`) must strictly adhere to [docs/styleguide.md](docs/styleguide.md). Any new styles or design changes (after dev approval) must first be updated in the style guide (or recorded as a pending item/todo in `docs/styleguide.md`) before being implemented in code.
16. **Ask which environment before touching live data**: any question that involves live data — the
    database, running containers, logs, checking whether something "actually works" — is ambiguous between
    production (192.0.2.27, see [.production](.production)) and the local dev stack (localhost) until
    stated otherwise. Ask which environment is meant before querying either one; do not assume localhost
    just because that's where the checkout lives.

## Production

Production info can be found at .production

Secrets not already in `.production` (or anything else in password manager) can be pulled via
`scripts/vw.sh` — a wrapper around the `bw` CLI. It needs a one-time, human-only setup (see the
script's header comment); an agent should never create or populate that local credentials file
itself.
