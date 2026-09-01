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
| `services/muma-mobile` | Kotlin / Android (Gradle) | n/a (client) | n/a | local (Room, on device) |
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
- Test: Vitest (jsdom) via `npm run test:unit` / `npm run coverage`, sources in `tests/unit/` (`store`,
  `downloaderTiming`, `genreCuration`); browser smoke test in `tests/browser/` via Playwright. Run in CI by
  `scripts/test/frontend-unit.sh` (lint + `svelte-check` + coverage) and `scripts/test/frontend-browser.sh`.
  Component rendering is covered for a handful of screens (`generalSettings`, `librariesTab`,
  `scannerTab`, `artistImagesTab`, `usersTabSubsonicToken`, `aboutSettings`); the rest of the unit
  tests target the plain-JS modules the components delegate to
- **Least-covered part of the repository**: 235 tests over 54 components, ~22% statements. The
  `thresholds` in `vite.config.js` are a ratchet just under the current numbers so it cannot erode;
  raise them as coverage climbs
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
- Own `db_init.sql`, `requirements.txt`, still no tests
- The only remaining large uncovered block in the Python suite (~715 statements at 0%). Its dependencies (`sqlalchemy`, `pandas`, `scikit-learn`, `joblib`) are in its own `requirements.txt` but not in the repo root one, so tests for it would either need those added to the CI environment or an `importorskip` guard that makes them silently skip there
- Compose service is commented out in `docker-compose.yml` (inactive)

### music-management-server (C++)
- Formatting: `./scripts/test/muma-server-format.sh` (`quality:cpp-format`), clang-format pinned
  to 20.1.8 via `silkeh/clang:20` — the version matters, releases disagree about output.
  `--fix` rewrites in place. `ColumnLimit: 0` in `.clang-format` means lines are never reflowed
- No other static analysis. clang-tidy has a config (`.clang-tidy`) that nothing runs; it needs
  the compilation database, so it belongs with the build rather than in a quality job
- Test: `./scripts/test/muma-server-unit.sh` builds and runs the CTest/GTest suite inside
  `Dockerfile-build-alpine` and extracts coverage

### muma-mobile (Android/Kotlin)
- Build: Gradle (`build.gradle`, `libs.versions.toml`), JVM target 21, uses `detekt` + `ktlintGradle`
- Test: JVM unit tests present under `services/muma-mobile/app/src/test/kotlin/...` (e.g. `ArchitectureTest`, `imageloader/*Test`, `domain/*Test`)
- Static analysis in `muma-mobile:check`: ktlint formatting
  (`./scripts/test/muma-mobile-ktlint.sh`, no baseline — `ktlintFormat` fixes what it finds),
  detekt (`./scripts/test/muma-mobile-detekt.sh`, per-module `detekt-baseline.xml`) and
  Android Lint (`./scripts/test/muma-mobile-lint.sh`, `:app:lintDebug` with
  `checkDependencies=true` so the core modules are analyzed too; pre-existing findings in
  `app/lint-baseline.xml`)
- Release-build smoke: `./scripts/test/muma-mobile-emulator-smoke.sh` boots the R8-minified
  APK on a headless ATD emulator (needs `/dev/kvm`) and fails on a startup crash — the class
  of defect (bug-report 029) every JVM-side check is structurally blind to
- No instrumentation/Android Auto tests beyond that smoke tripwire (UI flows still uncovered)

### common
- Shared helpers (`config_store.py`, `db_init.py`, `job_manager.py`, `step.py`, `version_helper.py`) — partly covered directly (`TableHelperTest.py`, `FilterTableHelperTest.py`, `LookupTableHelperTest.py`, `FestivalHelperTest.py`, `NotificationServiceTest.py`, `ProcessedFilesHelperTest.py`), the rest indirectly via dependent modules

## Database integration tests (`tests/integration/`)
- Runs every endpoint's SQL against a throwaway MariaDB: `./scripts/test/db-integration.sh`.
- Lives outside `services/` on purpose. pytest only loads conftest files along the path to a
  test, so from there the real `pymysql` is used rather than the `mock_base` stub -- which is
  the entire point, since everything under `services/` mocks the cursor.
- Builds the schema the way a deployment does: `services/common/db_init.py`, then every
  router's `init_db()`, then every `migrate_*.sql`. The migrations are applied twice, so one
  that is not re-runnable fails here rather than on deploy.
- Covers 37 read endpoints (every GET that touches the database), the user lifecycle, dynamic
  playlists under all four sort methods, genre curation and expansions, library reads,
  scrobble matching, and the download-account round trips.
- **Adding a read endpoint means adding it to `READ_ENDPOINTS` in
  `tests/integration/test_router_sql.py`** -- that list is what keeps the gap closed.

## Existing root-level test infrastructure
- `pytest.ini`: `pythonpath = services .`, test patterns `*Test.py` and `test_*.py`, `norecursedirs = modules/scrobbler`
- `conftest.py` (repo root): excludes `tools/test_fetcher_trace.py`, a hand-run diagnostic script that matches pytest's discovery pattern but contains no tests
- `scripts/test/music-management-unit.sh` collects everything under `services/` and `tools/`. It used to carry a hand-maintained allow-list of directories and files, which silently left about half the existing test files out of both the run and the reported coverage; discovery is now governed by `pytest.ini` and the root `conftest.py` alone, so a new test file needs no script change
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
2. Frontend: Vitest is in place; what is still missing is component-level rendering coverage
   (`@testing-library/svelte` is installed but unused).
3. The pre-commit hook mentioned in `AGENTS.md` was not found as a file — needs verification.
4. Downloader tests that may perform real external calls need to be mocked for CI (Phase 3.2).
5. `ml-analyzer` has no visible tests and its compose service is disabled — a scope decision is needed on whether it's included in Phases 1–3.
6. MuMa Mobile instrumentation/Android Auto tests: not yet found, needs a separate inventory pass once Phase 6 is addressed.
7. `docker/Dockerfile.music-manager` runs `COPY .env /app/.env`, baking the real `.env` (with real secrets) into every built image. This is safe at runtime for `compose.test.yml` because `load_dotenv()` defaults to `override=False`, so container `environment:` values still win — but it's bad image hygiene (secrets end up in image layers) and should be fixed later (tracked as a follow-up, not done in Task 3).
8. **Production config likely has the same bug as the Task 6 scrobble/rating URL fix.** All `music_manager` routes are mounted under `/api/*` (`main.py`: `app.include_router(..., prefix="/api/...")`), and this is what `UserSynchronizer.cpp` (`/users/`) and `MusicManagementPasswordService.cpp` (`/auth/login`) assume when appending directly onto `music-management-url`. On the production host (192.0.2.27, read-only SSH inspection), the deployed `LMS_MUSIC_MANAGEMENT_URL` is `http://192.0.2.27:8003` — **without** an `/api` suffix. This strongly suggests LMS→MusicManagement scrobbling/rating/user-sync is currently broken in production too, for the same root cause fixed in this session's `MusicManagementBackend.cpp` changes (scrobbling + feedback). Recommended fix: update the production `LMS_MUSIC_MANAGEMENT_URL` env var to `http://192.0.2.27:8003/api` (or the internal Docker service equivalent) once this fix is deployed. **Not changed in this session** — production was only inspected read-only, per explicit agreement; a production env change needs a deliberate, monitored rollout.
9. Production (`docker-compose` v1.29.2, legacy) uses prebuilt Docker Hub images (`muma/lms:stable`/`:alpha`, `muma/music-manager:latest`, etc.) rather than building from the current checkout like `compose.test.yml` does. MariaDB version (10.6) matches, which is good for compatibility. `docker compose` v2 (used implicitly by `compose.test.yml`'s syntax) was not found on production; `docker-compose` v1 is present instead — worth confirming compatibility (or upgrading the runner/host) before ever pointing production at the new compose files. Also noted in passing: `muma-telegram-worker` was in a restart loop on production at inspection time — pre-existing, unrelated to this session's changes.
