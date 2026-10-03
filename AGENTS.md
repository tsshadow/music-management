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
- **Release folder without audio**: the Mover deletes a queue folder that holds only scene files
  (`00-*.m3u`, `.nfo`, `.sfv`, cover) instead of placing it, with an `INFO` event; audio at any
  depth, an unextracted archive or any other file keeps it (`services/common/audio_less_folder.py`,
  bug report 147).
- **Catalogue numbers**: `services/common/catalogue_number.py` is the one test of what a catalogue
  number looks like (letters and digits, at least one digit, no title words like `Anthem`/`Edit`,
  not a bare year). A folder name without one keeps its name -- no ` - ` prefix (bug report 145).
- **Release info**: when the name does not route a release, the importer reads its `.nfo` (label,
  `Company`, catalogue number, store link) and the Deezer album it links, cached in
  `release_store_lookups`, and places it under the existing label folder they name
  (`import_place_by_label_name`) -- unless the curator filed releases with that `.nfo` label in
  another folder: then it proposes both and remembers his one choice per label
  (`rules_label_name_choices`, #164). Deezer is asked only by the importer (four a second, budget per
  cycle); offline, everything falls back to today's behaviour.
  [docs/designs/release-info-enrichment/](docs/designs/release-info-enrichment/functional.md).
- **Import queue location**: `import_folder_path` (default: `__TODO` inside `eps_folder_path`). Any code
  that walks the label tree asks `services/common/import_queue.py` (`ImportQueue`) whether a folder is the
  queue or a label -- never compares against the name; `tests/ci/test_import_queue_predicate.py` enforces
  it. Moving the queue is that setting plus a folder move (bug report 087).

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
    - `LabelSong`: Mapping folder structures to Publisher/Catalog tags and copyright strings. A folder
      that names no label -- the import queue, a `_` folder such as `__Free&None`, a release folder
      in the label's place -- yields an empty publisher; `ImportQueue.is_placeholder_publisher` is
      the one predicate the tagger, the importer's label proposals and the scanner share (bug
      report 146).
- **Rules**: A flexible rule engine (`services/tagger/Song/rules/`) that handles:
    - Genre inference based on artists or subgenres.
    - Artist normalization (casing, splitting featured artists).
    - Artist rules match titles only against *trusted* names (`TrustedArtistHelper`): approved in
      artist curation, or already in the library before the queue was wired up. A name the scanner
      records later is pending until decided, so a guessed artist cannot confirm itself.
    - Release and series markers in download titles (`｜ Q-dance presents SPEQTRUM`, `(Gearbox
      Presents Lockdown 3.0)`, a trailing `｜ <channel>`) are stripped before the artist split and
      the release becomes ALBUM over an empty or channel-default album
      (`services/tagger/Song/title_markers.py`, [docs/designs/release-series-markers/](docs/designs/release-series-markers/technical.md)).
    - Remixer extraction from titles and assignment to `REMIXER` tag.
    - Release date of a label release by a precision ladder -- Deezer date (cached), `.nfo`
      release/street date, the file's own full date, `.nfo` rip date, arrival date -- written to
      ORIGINALDATE with its rung in `DATE_SOURCE`; a worse rung never replaces a better one
      (`InferReleaseDateFromNfoRule`). Backlog: `scripts/prod/person/backfill-release-dates.sh`.
    - Cleanup of invalid characters (e.g., zero-width spaces).
    - Channel links: a SoundCloud/YouTube download whose channel a curator linked to a label or artist
      (Beheer → Downloaders → Koppelingen, by proposal or by hand) gets that label as its publisher and
      the linked artist in place of the channel name standing in for one (`ApplyChannelLinkRule`,
      [docs/designs/channel-links/](docs/designs/channel-links/functional.md)).
- **Background Task**: Managed via a background thread in `music-manager`.

### 4. `scanner` (Integrated in `music-manager`)
- **Role**: Synchronizes the filesystem with the database.
- **Features**:
    - **Metadata Extraction**: Reads tags from audio files and updates the `library_tracks`, `library_artists`, etc., tables.
    - **REST API**: Integrated into `music-manager` (Port 8000) under `/api/scanner`:
        - `POST /api/scanner/scan/all`: Runs a full library scan in background.
        - `POST /api/scanner/scan/file?path=...`: Scans a single file and updates its database record.
        - `GET /api/scanner/health`: Health check and status.
    - **Failure handling**: a tag value longer than its column is cut to the column's character
      length and the file is queued for a retag (`overlong_tag`); a file whose scan fails three
      times in a row, unchanged, is parked until it changes or the service restarts (bug report 117).
    - **Track form**: every track gets a `form` (`track` / `set` / `liveset` / `podcast`) and, for a
      live set whose festival edition is known, a `performance_date` -- derived from path, title and
      duration by `services/common/track_form.py`, written by the scanner and settled hourly (plus
      pushed into LMS `track.form`) by `track_form_sync.py`. See `docs/designs/track-form/`.
    - **Redownload Service**: Allows triggering redownloads for tracks that originated from SoundCloud or YouTube.
        - Automatically matches library tracks to original source URLs using the download archive.
        - `POST /api/library/tracks/{id}/redownload`: Starts a background redownload task.

### 5. `music-management-server` (`services/music-management-server`)
- **Role**: The high-performance playback and streaming engine.
- **Backend**: C++/SQLite based server providing audio streaming and Subsonic API.
- **Data Scope**: Maintains a volatile database (`lms.db`) for indexing local files and managing playback state.
- **UI**: Unified Svelte-based "Spotify UI" that includes both playback and system management.
- **Fork**: a hard fork of upstream LMS v3.76.0, not kept in sync. Upstream base, MuMa-specific
  files, the database migration-number policy and how to port an upstream fix are in
  [services/music-management-server/FORK.md](services/music-management-server/FORK.md) -- read it
  before adding an LMS migration or bringing in upstream code.

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

### 7. `bpm-analyzer` (`services/music_manager/bpm/worker.py`, container `muma-bpm-analyzer`)
- **Purpose**: Measures every track's tempo (0.01 BPM) from a 60 s excerpt, newest tracks first, into
  `library_track_bpm`, for browse by BPM (`/api/library/bpm`, docs/designs/bpm-browse/).
- **Runs**: its own container from the tools image (needs ffmpeg), capped at 2 cores / 768 MB, analysis
  processes at nice 19 / idle I/O. Settings on Beheer → Config → BPM (on/off, pause, workers,
  excerpt), read from music-manager's `config.json` every round.
- **Tag writeback**: the analyzer never writes files (its share mount is read-only). The tagger round in
  music-manager ends with a capped step (`services/music_manager/bpm/tag_writeback.py`, default 300 files
  per round, after the retag queue) that writes confident measurements into the files' own BPM tag
  (ID3 `TBPM`, MP4 `tmpo`, Vorbis `BPM`), leaving matching and genuine tags alone
  (docs/designs/bpm-tag-writeback/).

### 5. `ml-analyzer` (`services/ml-analyzer`)
- **Deprecated — see [services/ml-analyzer/DEPRECATED.md](services/ml-analyzer/DEPRECATED.md).**
  Disabled since 2026-09-25 with the code kept: it was never deployed, has no owner time, and
  would not work if it ran (wrong skip key, bug 028's stale join key on the ML labels, a predict
  step that does not match its trainer). Not built, deployed or tested by default; its tables and
  their data stay for the features that read them.
- **Purpose** (when it ran): tempo (BPM), loudness, spectral and timbre features (MFCC, chroma)
  with librosa, plus a scikit-learn genre classifier. No key or mood detection.

---

## 🔄 System Workflow

1. **Ingestion**: A new track enters via `downloader`, `importer`, or `telegram`.
2. **Standardization**: The `tagger` service applies site-specific or label-specific rules to ensure metadata consistency.
3. **Database Update**: Metadata and tracking information are saved to the MariaDB `music_management` database.
4. **Library Placement**: The file is moved to its permanent location in the music library.
5. **Server Sync**: Music Management Server rescans the library, making the music available for playback.
6. **Notification**: An `INFO` event with `push=True` is emitted, its message formatted via
   `BaseSong.__str__`. It is written to the event log and, because push was requested, also relayed
   to the user's mobile device via ntfy. The importer pushes once per release instead (label,
   catalogue number, track count) and records each track as an `INFO` event without a push.

---

## 🔔 Events & Alerts

Every service writes structured events (`INFO`/`WARNING`/`ERROR`/`CRITICAL`) directly to the `events`
table through `EventService`; that table is the source of truth, not `ntfy.sh`. Each event then fans
out to every registered sink, of which ntfy is currently the only one — so an event still exists,
queryable via `GET /api/events`, even if ntfy itself is unreachable. This is the reverse of the
pre-events design, where code POSTed to ntfy and a listener thread read it back to populate the
database.

Being the source of truth does not mean the push waits for the row. `EventService` runs two
threads: the event worker hands each event to the database writer's own queue and then dispatches
it to the sinks at once, and the writer does the INSERT with its retries (1 + 4 + 16 s). During a
MariaDB outage the rows are late and the pushes are not — before the split a `CRITICAL` queued
behind N events waited N x 21 s for its push. The writer keeps its own un-pooled connection on
purpose: the module also runs in the downloader and importer, and the event log has to work when
the API's pool is exhausted.

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
per service — only the `logger` column is uninformative for those rows. `services.music_manager` is
on the list too, for the modules that name their logger after themselves (`getLogger(__name__)`:
the song-version sync, the track-form push, the release-date sync, the feeds); their hourly
summaries used to exist only in `docker logs` (bug report 105). `QUIET_PREFIXES` keeps
`services.music_manager.artist_image_fetcher` at `WARNING`, because it logs per artist. Filtering `/api/events` by
source therefore offers four values: `music-manager`, `downloader`, `importer`, `bpm-analyzer`. The tagger
and scanner loops run as threads inside the music-manager process and emit under its source.

### Retention: how long an event stays
The `events-retention` loop (`services/music_manager/events_retention.py`) deletes events per level
once a day: `DEBUG` after 3 days, `INFO` 14, `WARNING` 30, `ERROR` 90, `CRITICAL` 365 — configurable
as `events_retention_<level>_days` on the Beheer config page (group *Events*). It picks at most 10k
ids per statement through the `(level, created_at)` index and deletes them by primary key, pausing
between batches, and stops after 5 minutes; a pass cut short comes back after an hour instead of a
day, so a backlog is worked off in hourly passes. If the table still holds more than
`events_max_rows` (default 10 million) afterwards, the oldest `DEBUG`/`INFO`, then `WARNING`, then
`ERROR` rows go; `CRITICAL` is never removed by size, and a pass that needed the cap logs a
`WARNING`. Each pass logs one summary line at `INFO` on `music-manager.events-retention`. Every
`WARNING`+ still reaches the table; retention only decides how long it stays. Deleted rows do not
shrink the InnoDB file — reclaiming the space is an operator step, see `docs/deployment.md`
("Reclaiming space in the events table") and bug report 072.

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
`version`, `database` (`ok`/`unreachable`), `threads` and `heartbeats`, and returns HTTP 503 when
any of those is unhealthy — instead of the old hard-coded `ok`. This is what makes the existing
Uptime Kuma monitor on that endpoint meaningful; nothing needs to change on the Kuma side.
It also carries `bpm_analysis`, the bpm-analyzer container's own status file (state, analysed,
failed, remaining, rate, ETA), mirrored as a `bpm-analyzer` entry in `heartbeats`; that one never
affects the status code, because /health is also music-manager's own container healthcheck.

- `database` is `SELECT 1` on its own short-lived connection (1 s timeouts, 2 s deadline), never a
  pooled one: the pool only pings a cached connection when a query runs, and an exhausted pool must
  not make the check wait. `/health` therefore always answers within about two seconds.
- `threads` has one boolean per long-running loop — `tagger`, `scanner`, `radio`, `news`,
  `events-retention`, `scrobble-rematch`, `song-versions`, `feeds-refresh`, `lms-db-sync`,
  `lms-listen-backfill`, `artist-auto-approve` — plus `events` for the event worker and writer. A loop is `true` when its thread is alive **and** its
  heartbeat (the last *completed* tick) is younger than its window: three intervals with a one-hour
  floor, except `tagger` 24 h (a round may include the daily walk), `scanner` 12 h, `news` 3 h
  (it sleeps up to an hour inside its tick), `lms-listen-backfill` 72 h (its interval is a
  config key that can be raised at runtime) and `artist-auto-approve` 72 h (it checks hourly, but
  a round of external lookups may take up to three hours). The window counts from startup, so a fresh process is
  green. `heartbeats` carries the detail per loop: `alive`, `stale`, `last_tick_age_seconds`,
  `stale_after_seconds`, `ticks`, `failures`.
- Every loop runs through `thread_registry.run_forever`: an exception in a tick is logged with
  `logger.exception` (an `ERROR` event from logger `music-manager.threads`), followed by a backoff
  of 10 s doubling up to the loop's interval, and the loop carries on. `scrobble-rematch`,
  `song-versions` and `lms-db-sync` wait their full interval after a failure instead, as they always
  did. A new loop goes through `run_forever` too, or a single exception ends it for good.
  `lms-listen-backfill` catches its own failures instead: one `WARNING` per run of failures, so a
  missing `lms.db` does not raise an `ERROR` every quarter of an hour (bug report 075).
- `lms_listen_outbox` lists, per LMS database, how many listens LMS still holds for
  music-manager in its outbox (`muma_listen_outbox`, LMS db version 125+) and when the oldest was
  queued. It is informational and never turns `/health` red: listens wait there through every
  music-manager restart. LMS delivers them in order with backoff, and it logs a `WARNING` for each
  one it drops (over 10,000 waiting, older than 14 days, or refused as malformed). See
  `docs/designs/lms-listen-outbox/`.
- A request that finds every pooled connection busy for `DB_POOL_WAIT_SECONDS` (default 5) gets a
  503 with `Retry-After`, rather than waiting forever.

---

## ⚙️ Runtime Configuration

`services/common/config_store.py` (`ConfigStore`) holds the runtime settings; Beheer > Configuratie
renders its schema (`GET /api/config/fields`) and saves through `POST /api/config`. Precedence,
highest first:

1. a value changed through the API, persisted in `data/config.json` (mode 0600);
2. the environment, read at start-up;
3. the field's declared default.

Only (1) is written to disk, and only while it differs from what the environment or default would
give: setting a key back to its environment value removes it from the file, so the next deploy's
environment applies again. Secrets that come from the environment are never written. Up to 0.72
the store wrote every value — secrets included — and loaded the file after the environment, so a
snapshot from the day of the first save beat every later deploy. Such a legacy file (no
`__format__` marker) still loads, except entries equal to env/default, secrets the environment
also sets, and read-only fields; it is rewritten in the new format on the first start.

Secrets leave the process only as `SECRET_SENTINEL`, on reads and in the `POST` response alike.
The `db_*` fields are `read_only`: the database connection is opened from the environment
(`DatabaseConnector`, `database.py`), so the page shows them for information and the API refuses
a change. The LMS Subsonic key has one resolver, `LmsEndpoint.resolve_lms_api_key()` (store, then
`MUMA_SERVER_SUBSONIC_API_KEY`/`LMS_SUBSONIC_API_KEY`), used by both the radio scheduler and the
scan trigger; anything that logs an LMS error passes it through `redact_url()` first, because the
key travels in the query string.

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
    - Synchronizes application settings (stored as JSON) to the `music-manager` API (`POST /api/users/{id}/settings/ultrasonic`, read back with `GET` on the same path).
    - The account settings it shares with the web player (`app_id=frontend`: favourite genres, set
      resume positions) are written per key with `PATCH` on the same path, so the phone, a tablet
      and the web never overwrite each other's changes; `POST` still replaces a whole blob for
      older app versions.
    - Provides a seamless transition when switching devices or re-installing the app.
- **Real-time Feedback**:
    - **Ratings**: Star ratings changed within MuMa Mobile are sent to LMS via the Subsonic API and then webhooked to `music-manager`.
    - **Scrobbles**: Playback history is reported via LMS to the central scrobbling engine.
- **Distribution**: Updates are managed via a dedicated `apk-hoster` service, allowing for independent delivery outside of app stores.

---

## 🧪 Testing & Stability

To maintain high code quality, the system employs an automated test suite:
- **Location**: next to the code under `services/` (`tests/` directories and `*Test.py` files), plus
  `tools/`, `tests/ci/` (pipeline policy) and `tests/unit/` (tests that need a real library the
  `services/` stubs replace) — all collected by `scripts/test/music-management-unit.sh`. The suites
  that need a live database or stack live under `tests/integration/`, `tests/contracts/` and `tests/bdd/`.
- **Mocking**: `services/tests/mock_base.py` offers stubs for `mutagen`, `yt_dlp`, `pymysql`, `config_store`,
  `Cache`, `DatabaseConnector` and more, **opt-in per test module**: a module declares what it relies on with
  a module-level `pytestmark = pytest.mark.mock_base('mutagen', 'Cache')` (literal names only; the marker is
  read from the source before import, so it cannot go on a class or test). `services/tests/mock_base_plugin.py`
  installs those stubs only while that module is imported and its tests run, and lifts them -- and every
  project module imported under them -- out of `sys.modules` afterwards. A module without the marker gets
  the real libraries. Never put a MagicMock into `sys.modules` by hand outside `patch.dict`;
  `tests/ci/test_mock_base_isolation.py` fails if a stub is still there after collection (bug report 085).
- **Enforcement**: 
    - **Build Check**: `build.sh` runs pylint over `services/` (floor 8.5) and a subset of the unit tests
      (`services/downloader/soundcloud/tests/`, `services/importer/tests/`,
      `services/tests/YoutubeDownloaderTest.py`, `services/music_manager/tests/`) and aborts the
      container build if either fails. It is not the full suite: CI's `backend:unit` is.
    - **Pre-commit Hook**: The versioned `scripts/hooks/pre-commit` (installed by `./scripts/install-hooks.sh`)
      runs `./scripts/lint.sh` and `./scripts/test/music-management-unit.sh` before a commit is
      finalized; `SKIP_HOOK_TESTS=1` skips the tests, not the lint.
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
- **Quality gates** — enforced in CI (`quality` stage). The versioned pre-commit hook
  (`./scripts/install-hooks.sh`) is a thin wrapper around the same scripts so the two cannot
  drift, but it runs only `format.sh --check`, `lint.sh` and the Python unit suite — not the
  type check:
    - `./scripts/lint.sh` — ruff (config in `pyproject.toml`) + pylint, threshold 9.77. On a full
      run it also fails any module on the strict type-check list that has an undocumented public
      function or class (rule 5 below); `.pylintrc` still disables those checks for the rest.
    - `./scripts/typecheck.sh` — mypy. Rolled out per module: `pyproject.toml` holds a loose
      floor for the whole tree and lists the strictly-checked modules. That list only grows.
      `backend:typecheck` runs the strict list; `backend:typecheck-all` runs `--all`, the whole
      tree at the loose floor. Both are hard gates: a new error fails the pipeline.
    - `./scripts/format.sh` — `ruff format` over `services/`, `tools/` and `tests/` (or the
      paths you name). `--check` is the `backend:format` job, so an unformatted file fails the
      pipeline; run the script without `--check` to fix it.
    - `./scripts/ci/dependency-audit.sh` — pip-audit + npm audit. Runs on a schedule and on the
      default branch, not as a merge-request gate (it audits the runner's environment, which
      this repository does not manage). Accepted findings, with a reason, live in
      `security/accepted-vulnerabilities.txt`.
- **Ratchets** — `FAIL_UNDER` in `scripts/lint.sh` (9.77), `COVERAGE_MIN` in
  `scripts/test/music-management-unit.sh` (84%) and the `thresholds` in
  `services/frontend/vite.config.js` are floors. Raise them as the numbers climb; never lower
  one to make a red build green. The Python coverage figure is measured on source only —
  `services/` and `tools/`, with every test and fixture file omitted (`[tool.coverage.run]` in
  `pyproject.toml`); 84.89% when that was introduced. `COVERAGE_MIN` went from 93 to 84 then,
  the one sanctioned exception to this rule: the old figure counted the tests themselves as
  covered code (bug report 047).
- **Uniform local test scripts** (`scripts/test/`), run the same way locally and in CI:
    - `./scripts/test/music-management-unit.sh` — Python unit tests: `services/`, `tools/`,
      `tests/ci/` and `tests/unit/`, with the coverage gate. In CI this and `db-integration.sh`
      run pytest inside `docker/Dockerfile.python-ci` (python:3.14-slim, the images' Python) with
      `requirements.txt` installed — not on the runner's own `python3`;
      `PYTHON_TOOLING_FORCE_CONTAINER=1` does the same locally. A test dependency therefore has
      to be in `requirements.txt`.
    - `./scripts/test/db-integration.sh` — every endpoint's SQL against a throwaway MariaDB
      (13.0, like production; `MARIADB_VERSION=10.6` for the old server), plus the schema
      bootstrap and every `migrate_*.sql` applied twice. The unit suite mocks the cursor, so this
      is the only thing that proves MariaDB accepts the queries. It also builds the schema twice
      from nothing — the fresh-stack way and the migrations way — and fails on any column or
      index that differs (`tests/integration/test_schema_drift.py`). In CI a database it cannot
      reach is a failure, not a skip.
    - `./scripts/test/muma-server-unit.sh` — LMS C++ unit tests (existing upstream CTest/GTest suite).
    - `./scripts/test/frontend-unit.sh` — frontend lint + svelte-check + vitest with coverage.
    - `./scripts/test/android-unit.sh` — MuMa Mobile JVM unit tests.
    - `./scripts/test/core-smoke.sh` — builds and starts `docker/compose.test.yml` from a clean state, waits for all healthchecks, then tears down.
    - `./scripts/test/contracts.sh` — LMS/OpenSubsonic contract tests + listen/scrobble flow, against the test stack + fixture track.
    - `./scripts/test/frontend-browser.sh` — Playwright browser tests (login, fixture track visible) against the test stack.
    - `./scripts/test/core-e2e.sh` — the server chain, as Gherkin under `tests/bdd/features/`: the scan-to-listen walk, the listen that matches nothing, the rating hop from LMS, genre curation, and access control. Gates every pipeline as `muma:e2e`. 45s to 90s, almost all of it waiting for three containers to report healthy — that wait swings with how loaded the runner is, while the tests themselves are ~4s. Needs `pytest-bdd`, and falls back to the tooling container when it is missing, as the runners' Python is.
      - The feature files are the description; the step code is not. If they disagree the feature file is right and the code is the bug.
      - Most of the setup is other people's state. LMS has no users of its own, so an account is created in `music-manager` and synced across, a library declared and scanned. Every `migrate_*.sql` is applied, because that is what a deploy does and what seeds `rules_genres`. And the tagger runs before either index is built — it is the only thing that registers a genre for curation, and it rewrites the file, so indexing before it leaves LMS serving new bytes under an old size.
- **Test stack**: `docker/compose.test.yml` — temporary MariaDB, `music-manager` and `music-management-server`, all built from the current checkout, disposable volumes, healthchecks. Never mounts real music/library paths or production data. LMS's disposable `lms-data` volume is also mounted into `music-manager` at `/app/data/stable`, where production mounts the real one, so everything that opens `lms.db` directly (the hourly sync, the listen backfill, `GET /api/auth/subsonic-token`) runs against the file LMS serves from; `music-manager` therefore starts only once LMS is healthy.
- **Fixture track**: `tests/fixtures/music/ci-test-track-001.mp3` (generated tone, no commercial audio) with expected metadata documented in `tests/fixtures/expected/ci-test-track-001.json`.
- **A new endpoint that reads the database** belongs in `tests/integration/test_router_sql.py`
  as well as in a unit test. **A schema change needs two edits**: the `CREATE TABLE` in
  `services/common/db_init.py`, a re-runnable `migrate_*.sql` in the repository root (applied
  on every deploy by `scripts/deploy.sh`), and the same shape in both — the expected-table
  set is read from the `CREATE TABLE` statements themselves, and `test_schema_drift.py` fails if
  the two paths end in different columns or index names (name an index in the CREATE the way the
  migration names it). `CREATE TABLE IF NOT EXISTS` never alters an existing
  table -- that is how `downloads_youtube_accounts.channel_id` and
  `library_track_ml_labels.updated_at` went missing until the integration suite caught them.
  The deploy records each applied file with its sha256 in `schema_migrations` and skips it while
  it is unchanged (`tools/apply_migrations.py`), so editing an applied migration re-runs it on the
  next deploy -- it must stay re-runnable all the same.
  The migration must also be **expand-only**: `scripts/deploy.sh` applies it while the previous
  release is still running, before the new containers start. Dropping, renaming or narrowing
  what the running code reads waits for a later release (`tests/ci/test_migration_ordering.py`,
  `docs/deployment.md#deploy-order-and-migrations`).
- **Multi-statement writes go through `transaction(conn)`** from `services/music_manager/database.py`:
  the pool runs autocommit, so a DELETE-then-INSERT (or any write that must land whole) without it
  is two separate commits, and `conn.commit()` does not change that. Test it with
  `transaction_log` from `services/music_manager/tests/scripted_cursor.py`
  ([design](docs/designs/db-transactions/technical.md)).
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
Log files should be located in the log directory.
If for some reason a log file is not saved at that location, and you are done with it, move it to the log directory.
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
9. **Changelog required**: every functional change adds a fragment under `changelog.d/` in the same
   change (see [changelog.d/README.md](changelog.d/README.md)); `CHANGELOG.md` and `RELEASE_NOTES.md`
   are assembled from the fragments at release time and are not edited on a feature branch.
10. **API versioning / contract discipline**: a breaking change to a shared API (request/response shape,
    auth requirements) is called out explicitly in the technical design and the changelog, and is verified
    against [docs/testing-inventory.md](docs/testing-inventory.md)'s contract tests
    (`scripts/test/contracts.sh`) before it's considered complete.
11. **Ask, don't guess**: when a design doc doesn't cover a case, or a rule conflicts with a specific
    request, ask a clarifying question rather than silently choosing an interpretation.
12. **Living document**: this rule list is updated whenever the process changes — a stale rule is worse than
    no rule. If a single service's rules ever outgrow this root file, a nested `services/<name>/AGENTS.md`
    can be added later (none is needed today).
13. **Structured Bug Reports**: Every bug report is captured in a 2-step process using `docs/bug-reports/NNN-<title>.md`
    (three digits, the next free number — check the open branches too: five reports merged in parallel
    once all took 037, and four had to be renumbered to 053-056), containing:
    - `# title`
    - `# status: reported/analysed/fixed`
    - `# reported problem`
    - `# Possible reason`
    - `# solution`
14. **Open work lives in GitLab issues**: anything decided-but-not-done, or done-but-not-verified,
    becomes an issue in `muma/music-management` the moment it is found (`glab issue create`),
    not a line in a file. Each issue carries one kind label -- `needs-person` (Teun must run a
    script, check a device, enter a secret), `decision` (a choice only Teun can make), `verify`
    (check on production or a device after a release; state the exact check), `code` (buildable
    work), `deferred` (consciously parked) -- and one area label (`area-backend`, `area-frontend`,
    `area-mobile`, `area-lms`, `area-infra`, `area-data`). The issue links to the bug report,
    design doc or script where the detail lives: a bug report describes a fix, so it cannot carry
    a plan, and a merge request description is not a record. A merge request that finishes one
    writes `Closes #N` in its description; one that leaves something open files a new issue. The
    [Development board](https://gitlab.example.com/muma/music-management/-/boards/1) has a
    column per kind. [docs/open-work.md](docs/open-work.md) is only a pointer now (it held this
    list until 2026-09-26); do not add lines to it. A stale open issue is a bug, same as a stale
    design doc (rule 3).
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
