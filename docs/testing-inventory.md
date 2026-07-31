# Testing Inventory (Task 1)

> Goal: document the current situation before adding new test infrastructure.
> This inventory does **not** change any production logic. See `AGENTS.md` for the
> functional module description; this document focuses specifically on build/test/deploy facts.

## Module overview

| Module (path) | Language/Stack | Port(s) | Health endpoint | Database |
|---|---|---|---|---|
| `services/music_manager` (music-manager) | Python / FastAPI | 8000 (+8003 legacy) | `GET /health`, `/api/scanner/health`, `/api/tagger/health` | MariaDB (`music-management`, via `DB_*` env) |
| `services/music-management-server` (LMS) | C++ / Wt | 5082 | no explicit health endpoint; Subsonic `ping` can be used | SQLite (`lms.db`, own volatile DB) |
| `services/tagger` | Python (integrated into music-manager) | n/a | via music-manager | n/a |
| `services/scanner` | Python (integrated into music-manager) | n/a | via music-manager | n/a |
| `services/importer` | Python, standalone worker process | n/a | none | MariaDB (shared) |
| `services/downloader` (soundcloud/youtube/telegram) | Python, standalone workers | n/a | none | MariaDB (shared) |
| `services/ml-analyzer` | Python | n/a | none | own (`db_init.sql`) |
| `services/frontend` | Svelte 5 + Vite | 5173 (dev) | n/a (static build) | n/a |
| `services/ultrasonic` | Kotlin / Android (Gradle) | n/a (client) | n/a | local (Room, on device) |
| `services/common` | Python (shared helpers) | n/a | n/a | n/a |

## Per module — build / start / test / lint

### music_manager (FastAPI, port 8000)
- Build: `docker/Dockerfile.music-manager` (image `${IMAGE_CORE}`)
- Start: `uvicorn main:app` (via Docker `CMD`, or `python main.py`)
- Test: `pytest` (root `pytest.ini`: `pythonpath = services .`, patterns `*Test.py` / `test_*.py`)
  - Existing tests: `services/music_manager/tests/test_users.py`, `test_rating.py`
- Lint: `.pylintrc` (root), disables e.g. `missing-docstring`, `import-error`
- Env vars: `DB_HOST/PORT/USER/PASS/DB`, `API_KEY`, `AUTH_SERVICE_URL`, `MUMA_SERVER_HOSTS`, `MUMA_SERVER_SUBSONIC_API_KEY`, `NOTIFY_URL`, `STORAGE_PATH`, `PYTHONPATH`
- Migrations: no ORM migration tool found (root `migrate_v2.sql`, `migrate_v3.sql` — manual SQL scripts)
- External dependencies: MariaDB, music-management-server (Subsonic API), ntfy.sh, Spotify/Last.fm (artist images)
- Dockerfile: `docker/Dockerfile.music-manager`; compose: `docker/docker-compose.yml` (service `music-manager`)
- Test output: no JUnit/coverage config found; `pytest`/`coverage` are listed in `requirements.txt`

### music-management-server (LMS, C++, port 5082)
- Build: CMake + Ninja/Make, see `CMakeLists.txt`; release build via `Dockerfile-release` (multi-stage: frontend build first, then Alpine C++ build)
- Test: **CTest + GTest are already present upstream** (`include(CTest)`, `find_package(GTest REQUIRED)`)
  - Existing test targets (`gtest_discover_tests`): `test-podcast`, `test-scanner`, `test-scrobbling`, `test-subsonic`, `test-database`, `test-som`, `test-core`
  - ⇒ **No new test framework needed** for Phase 2, just run/extend the existing CTest targets.
  - How to run: `ctest` in the build directory (not yet confirmed to pass locally on the current commit — not executed in this step, no production changes allowed)
- Config: `conf/lms.conf` (`listen-port = 5082`, `docroot`, `db-integrity-check`)
- Lint/format: not found in this inventory pass (to check in a later step)
- Dockerfile: `Dockerfile-release` (Alpine, many system dependencies: ffmpeg, boost, gtest-dev, sqlite-dev, etc.)
- Compose: `docker/docker-compose.yml` (service `music-management-server`)

### frontend (Svelte + Vite)
- Build: `npm run build` (Vite)
- Start (dev): `npm run dev` (port 5173, proxy to `/api`→8000, `/rest`+`/muma`→5082, targets overridable via `VITE_API_TARGET`/`VITE_LMS_TARGET`)
- Test: **no unit test tool configured** (no vitest/jest in `package.json`) — gap vs. Phase 5.1
- Lint: `npm run lint` (`oxlint` + `eslint`), format: `npm run format` (`oxfmt`), typecheck: `npm run check` (`svelte-check`)
- Dockerfile: first build stage of `services/music-management-server/Dockerfile-release` (`node:24-alpine`) — frontend has no own Dockerfile under `docker/`

### importer
- Test: `services/importer/tests/` (6 files: mover, genre_rules, artist_rules, copyright, basic, unicode) — via root `pytest`
- Dockerfile: `docker/Dockerfile.importer`; compose service: `importer_worker`
- Env: `import_folder_path`, `eps_folder_path`, `music_folder_path`, `delimiter`, DB vars

### downloader (soundcloud/youtube/telegram)
- Test: `services/downloader/soundcloud/tests/` (8 files), youtube/telegram tests live in `services/tests/` (root-level: `TelegramDownloaderTest.py`, `YoutubeArchiveTest.py`, `YoutubeDownloaderTest.py`, `YoutubeSongProcessorTest.py`, `YoutubeSongTest.py`)
- Dockerfile: `docker/Dockerfile.downloader`; compose services: `youtube_worker`, `soundcloud_worker`, `soundcloud_worker_full_once`, `telegram_worker` (telegram uses `docker/Dockerfile.telegram`)
- Some download tests may make real `yt-dlp`/SoundCloud calls — still needs to be verified whether these are mocked for CI (Phase 3.2 concern)

### ml-analyzer
- Own `db_init.sql`, `requirements.txt`, no visible tests found in this pass
- Compose service is commented out in `docker-compose.yml` (inactive)

### ultrasonic (Android/Kotlin)
- Build: Gradle (`build.gradle`, `libs.versions.toml`), JVM target 21, uses `detekt` + `ktlintGradle`
- Test: JVM unit tests present under `services/ultrasonic/ultrasonic/src/test/kotlin/...` (e.g. `ArchitectureTest`, `imageloader/*Test`, `domain/*Test`)
- No instrumentation/Android Auto tests found in this pass (to confirm in a later step)

### common
- Shared helpers (`config_store.py`, `db_init.py`, `job_manager.py`, `step.py`, `version_helper.py`) — no own tests found, covered indirectly via dependent modules
- Exception: `services/common/Helpers/GenreRulesHelperTest.py` and `services/tagger/Song/rules/ResolveGenreRuleTest.py` are listed explicitly in `scripts/test/music-management-unit.sh`, since neither `services/common/Helpers/` nor `services/tagger/Song/rules/` is a CI target directory

## Existing root-level test infrastructure
- `pytest.ini`: `pythonpath = services .`, test patterns `*Test.py` and `test_*.py`, `norecursedirs = modules/scrobbler`
- `.pylintrc`: shared pylint config for all Python modules
- `services/tests/`: root-wide/shared Python tests + `mock_base.py` (mock base for `mutagen`, `yt-dlp`, DB helpers)
- `build.sh`: runs the full test suite and aborts the container build if any tests fail (mentioned in `AGENTS.md`)
- Git pre-commit hook that requires tests to pass before commit (mentioned in `AGENTS.md`, not yet found as a file in this pass)

## Docker inventory (Phase 1.2 — findings, not yet resolved)

File: `docker/docker-compose.yml` (533 lines, main compose) + `docker-compose.core.yml`, `.dev.yml`, `.full.yml`, `.tools.yml`, `.workers.yml`

Services found: `db` (MariaDB 10.6), `phpmyadmin`, `music-manager`, `music-management-server`, `importer_worker`, `youtube_worker`, `soundcloud_worker`, `soundcloud_worker_full_once`, `telegram_worker`, `soundcloud-fetcher`, `genre-processor`, `firefox`. Several services (control-center, tagger, scanner, ml-analyzer, rating-system, scrobble-service, user-service, stats-service, artist-image-fetcher) are **commented out**, ready for future decomposition.

Phase 1.2 checklist — status:

| Question | Status |
|---|---|
| Does every image build from a clean checkout? | ⚠️ Not yet verified (no clean build performed in this pass) |
| No local absolute paths? | ❌ `HOST_MUSIC_PATH`, `HOST_DATA_PATH`, `import_folder_path` etc. are absolute host paths in `.env` (e.g. `/mnt/music`, `/docker/music-management`) |
| Are all versions pinned? | ⚠️ Mixed: `mariadb:10.6` is pinned, but several images use `:latest` (`phpmyadmin:latest`, `${DOCKER_USER}/*:latest`, `jlesage/firefox:latest`) |
| Do services run as non-root? | ❌ No `user:` directives found in `docker-compose.yml` |
| Are volumes in the test environment temporary? | ❌ `compose.test.yml` does not exist yet; current volumes are persistent (host mounts) |
| Do databases have healthchecks? | ❌ No `healthcheck:` found on the `db` service or elsewhere |
| Do services wait until their database is actually ready? | ❌ `depends_on` does not use `condition: service_healthy` (because there are no healthchecks) — only start order, no readiness wait |
| Does `docker compose down -v` clean up everything? | ⚠️ Not yet tested |
| Can production data never accidentally end up in tests? | ❌ No separation: dev/prod use the same host mounts (`/mnt/music`, production DB path) — a dedicated `compose.test.yml` with its own temporary volumes is still missing |

These gaps are **not resolved in this step** (per Task 1: inventory only, no production changes). They form the basis for Task 3 (`compose.test.yml` + healthchecks).

## Open questions / follow-ups for later steps
1. LMS: confirm that the existing `ctest` suite actually passes locally on the current commit (Phase 2.1) — not yet run.
2. Frontend: no unit test tool is configured; one needs to be chosen (e.g. Vitest) in Phase 5.
3. The pre-commit hook mentioned in `AGENTS.md` was not found as a file — needs verification.
4. Downloader tests that may perform real external calls need to be mocked for CI (Phase 3.2).
5. `ml-analyzer` has no visible tests and its compose service is disabled — a scope decision is needed on whether it's included in Phases 1–3.
6. Ultrasonic instrumentation/Android Auto tests: not yet found, needs a separate inventory pass once Phase 6 is addressed.
7. `docker/Dockerfile.music-manager` runs `COPY .env /app/.env`, baking the real `.env` (with real secrets) into every built image. This is safe at runtime for `compose.test.yml` because `load_dotenv()` defaults to `override=False`, so container `environment:` values still win — but it's bad image hygiene (secrets end up in image layers) and should be fixed later (tracked as a follow-up, not done in Task 3).
8. **Production config likely has the same bug as the Task 6 scrobble/rating URL fix.** All `music_manager` routes are mounted under `/api/*` (`main.py`: `app.include_router(..., prefix="/api/...")`), and this is what `UserSynchronizer.cpp` (`/users/`) and `MusicManagementPasswordService.cpp` (`/auth/login`) assume when appending directly onto `music-management-url`. On the production host (192.0.2.27, read-only SSH inspection), the deployed `LMS_MUSIC_MANAGEMENT_URL` is `http://192.0.2.27:8003` — **without** an `/api` suffix. This strongly suggests LMS→MusicManagement scrobbling/rating/user-sync is currently broken in production too, for the same root cause fixed in this session's `MusicManagementBackend.cpp` changes (scrobbling + feedback). Recommended fix: update the production `LMS_MUSIC_MANAGEMENT_URL` env var to `http://192.0.2.27:8003/api` (or the internal Docker service equivalent) once this fix is deployed. **Not changed in this session** — production was only inspected read-only, per explicit agreement; a production env change needs a deliberate, monitored rollout.
9. Production (`docker-compose` v1.29.2, legacy) uses prebuilt Docker Hub images (`muma/lms:stable`/`:alpha`, `muma/music-manager:latest`, etc.) rather than building from the current checkout like `compose.test.yml` does. MariaDB version (10.6) matches, which is good for compatibility. `docker compose` v2 (used implicitly by `compose.test.yml`'s syntax) was not found on production; `docker-compose` v1 is present instead — worth confirming compatibility (or upgrading the runner/host) before ever pointing production at the new compose files. Also noted in passing: `muma-telegram-worker` was in a restart loop on production at inspection time — pre-existing, unrelated to this session's changes.
