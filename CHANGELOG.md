# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Automated `master` -> `develop` back-merge**: previously, after a `release/*` branch was merged
  into `master`, keeping `develop` in sync required manually opening and merging a second MR from
  the release branch (or `master`) into `develop`. Added `release:back-merge-develop`
  (`scripts/ci/back-merge-develop.sh`), a new CI job that runs on `master` right after
  `release:tag` and automatically opens+merges a `master` -> `develop` MR via the GitLab API,
  reusing the existing `TAG_CREATION_TOKEN`. It's a no-op if `develop` already contains `master`'s
  tip, and leaves the MR open for manual conflict resolution if the merge can't be done
  automatically.

## [0.0.33] - 2026-07-29

### Fixed
- **Ultrasonic Google Sign-In selected an account in the picker but then silently returned to the
  login dialog, with no error shown (`bug 013`)**: both `NavigationActivity.performWelcomeGoogleSignIn()`
  and `EditServerFragment.handleGoogleSignInResult()` checked the credential returned by
  `CredentialManager.getCredential()` with a naive `is GoogleIdTokenCredential`. Android's Credential
  Manager never delivers third-party credential types (like Google's) as their concrete subclass
  across the IPC boundary — they always arrive as a generic `CustomCredential` (a `type` string plus
  a raw `data: Bundle`), even though `GoogleIdTokenCredential` extends `CustomCredential` in the
  `googleid` library's own class hierarchy. The cast always failed, silently discarding a
  successful account selection before the ID token was extracted and before `/api/auth/google` was
  ever called. Replaced both checks with the documented pattern
  (`credential is CustomCredential && credential.type == GoogleIdTokenCredential.TYPE_GOOGLE_ID_TOKEN_CREDENTIAL`,
  then `GoogleIdTokenCredential.createFrom(credential.data)`), with an explicit logged/user-visible
  error path for any unexpected credential type or parse failure.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`239`/`6.5.9` -> `240`/`6.5.10`).

## [0.0.32] - 2026-07-29

### Added
- **Artist face images in the web player bar**: `Player.svelte` previously rendered only track
  cover art and plain artist-name text — no artist photo, unlike `ArtistView`, `Dashboard`,
  `SearchResults`, and `StarredView`, which already fetch artist images from `music_manager` via
  the shared `getArtistImageUrl()` helper. Reused that same helper to show a small circular
  avatar next to the artist name in both the mobile mini player and the desktop player bar, using
  the primary (first) artist of the currently playing track. No backend changes were needed — the
  manager's image-fetching/caching pipeline was already working, it just wasn't wired into the
  player UI.

## [0.0.30] - 2026-07-29

### Fixed
- **Ultrasonic welcome-screen Google Sign-In succeeded but the dialog never closed, leaving the
  app stuck requiring login (`bug 012`)**: `NavigationActivity.performWelcomeGoogleSignIn()`'s
  `"ok"` branch had been copied from the manual username/password submit handler just above it,
  including a `MusicServiceFactory.getMusicService().ping()` connectivity check gating whether the
  dialog was allowed to dismiss. That gate makes sense for manual credential entry (verifying
  arbitrary user-typed input), but not for Google Sign-In, where a `status: "ok"` response from
  `/api/auth/google` is already a server-verified, guaranteed-valid credential — the same trust
  model already used by `EditServerFragment.performMumaGoogleAuth()` and the web frontend's
  `handleGoogleResponse()`, neither of which re-verifies with a ping. A transient/unrelated
  connectivity hiccup on that extra ping call could silently discard an already-successful Google
  sign-in. Removed the ping-gating; the dialog now always closes on `"ok"`, exactly like the other
  two flows.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`238`/`6.5.8` -> `239`/`6.5.9`).

## [0.0.29] - 2026-07-29

### Fixed
- **Ultrasonic Google Sign-In still failed with "No Google accounts found" on a real device with
  a real Google account already signed in, even with a correct (non-placeholder)
  `GOOGLE_WEB_CLIENT_ID` (`bug 011`)**: two combined causes. First, `GetGoogleIdOption` (used by
  both `NavigationActivity.performWelcomeGoogleSignIn()` and
  `EditServerFragment.startGoogleSignIn()`), even with `setFilterByAuthorizedAccounts(false)`, only
  reliably returns a credential for an account that has already authorized this app before —
  switched both call sites to `GetSignInWithGoogleOption`, Google's dedicated option for
  not-yet-authorized/first-time sign-ins. Second, and more fundamentally, Google's Credential
  Manager backend refuses to issue any credential to a native Android app unless a separate
  **Android**-type OAuth client (package name + signing certificate SHA-1) is registered in the
  same Google Cloud project as the Web client ID — this is a manual, one-time Google Cloud Console
  step (not fixable purely in code/CI), documented in `docs/deployment.md` and
  `docs/bug-reports/011-google-signin-no-credential-real-device.md`, along with the two client
  registrations needed (one for the release keystore, one for the debug keystore).
- Corrected `docs/deployment.md` and `docs/designs/authentication/technical.md`, which previously
  (incorrectly) stated no separate Android OAuth client/SHA-1 registration was needed for
  Ultrasonic's Google Sign-In.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`237`/`6.5.7` -> `238`/`6.5.8`).

## [0.0.28] - 2026-07-29

### Fixed
- **Ultrasonic Google Sign-In showed a generic network error when no Google account exists on
  the device (`bug 010`)**: `CredentialManager.getCredential()` throws typed exceptions for
  distinct failure modes, but `NavigationActivity.performWelcomeGoogleSignIn()` and
  `EditServerFragment.startGoogleSignIn()` only had a catch-all `catch (e: Exception)`, so a
  device with no Google account (e.g. an emulator used for testing) always showed the same
  "network error" message as a real backend outage. Added explicit `catch` branches for
  `GetCredentialCancellationException` (silently ignored — user-initiated cancellation) and
  `NoCredentialException` (new, specific `google_signin_no_accounts` string: "No Google accounts
  found on this device."), both ordered before the generic fallback. Also logs a `Timber.e`
  warning in both call sites whenever `BuildConfig.GOOGLE_WEB_CLIENT_ID` is still the
  `"placeholder-id"` default, making a misconfigured build immediately visible in the logs.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`236`/`6.5.6` -> `237`/`6.5.7`).

## [0.0.27] - 2026-07-29

### Fixed
- **Ultrasonic welcome-screen "Sign in with Google" always failed with a network error
  (`bug 009`)**: the button added in `0.0.25` reused the app's shared, Koin-injected
  `SubsonicAPIClient.mumaApi`, which on a fresh install (before any server had been configured)
  was still built against the offline/`localhost` fallback server, so the Google auth request
  never reached the real backend. `NavigationActivity.performWelcomeGoogleSignIn()` now builds a
  dedicated Muma API client targeting the fixed production server address directly; extracted the
  Muma base-URL derivation into a reusable `SubsonicAPIClient.mumaBaseUrlFor()` so both call sites
  stay consistent.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`235`/`6.5.5` -> `236`/`6.5.6`).

## [0.0.25] - 2026-07-28

> **Two Ultrasonic (Android) fixes, requested together: the default server was still pointing at
> the retired "alpha" test instance, and the "Sign in with Google" option was missing from the
> very first login screen users see on a fresh install.**

### Changed
- **Default server is now `music.example.com`**: the separate "alpha" server entry (already
  retired at the infrastructure level, see `docs/deployment.md`'s "production-lms-consolidation")
  has been removed from Ultrasonic's static server list; there is now exactly one, fixed
  production server. Adjusted the (previously hard-coded) debug-build server selection, the
  "offline" pseudo-server's list index, and updated `docs/architecture.md`/`docs/OVERVIEW.md`
  which still described a live Alpha instance.
- **"Sign in with Google" is now available on the very first login screen** (the welcome dialog
  shown on a fresh install / after a full logout), not just from deep inside the server-edit
  screen — this was the actual requirement: a first-time user must be able to choose Google login
  immediately, without first setting up a username/password server entry. The new button reuses
  the exact same Credential Manager flow, response handling (nested `user`/`api_key` fields,
  access-request navigation for not-yet-linked accounts) and Subsonic-credential-population logic
  already fixed for the in-app flow in `0.0.23`.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`234`/`6.5.4` -> `235`/`6.5.5`).

## [0.0.23] - 2026-07-28

> **Ultrasonic (Android) now supports "Sign in with Google", functionally equivalent to the web frontend.**
> A native Credential Manager-based Google Sign-In flow already existed in the Ultrasonic codebase (button,
> access-request UX, token handling), but had two bugs that meant it could never actually work end-to-end.

### Fixed
- **Ultrasonic's `MumaAuthResponse` used a stale, flat response shape**: `/api/auth/google`/`/api/auth/refresh`
  return account fields nested under `user` (per the `0.0.4` fix to `/api/auth/login`/`/api/auth/google`), but
  the Android DTO still declared `id`/`username`/`display_name`/etc. as top-level fields, so they always
  deserialized as `null` after a successful Google sign-in. Added a `MumaAuthUser` nested type matching the
  real backend contract.
- **Ultrasonic never populated Subsonic/LMS credentials after a Google sign-in** (the exact same class of bug
  fixed for the web frontend in `0.0.6`): `EditServerFragment.performMumaGoogleAuth()`'s `"ok"` branch stored
  the MuMa access/refresh token but never wrote a username/password into the server's Subsonic fields, so
  streaming/library calls (and every other Subsonic request) stayed unauthenticated after a Google login. Now
  mirrors the web frontend exactly: writes `result.user.username`/`api_key` into `userNameEditText`/
  `passwordEditText`/`ServerSetting.userName`/`.password`, relying on the same `api_key`-as-password fallback
  in `/api/auth/login`.
- **Wired up the missing `GOOGLE_WEB_CLIENT_ID` build config value in CI**: the app's Google Sign-In flow
  already read `BuildConfig.GOOGLE_WEB_CLIENT_ID` (intended to equal the web's `GOOGLE_CLIENT_ID`), but no CI
  job ever provided a real value, so every CI-built APK shipped with the `build.gradle` default
  `"placeholder-id"`, making Google Sign-In silently non-functional. `scripts/ci/ultrasonic-build-upload.sh`
  now extracts `GOOGLE_CLIENT_ID` from the existing `PROD_ENV_FILE` CI/CD variable and passes it through — no
  new secret or Android-specific OAuth client registration required, since the Android flow reuses the web
  client ID as its Credential Manager `serverClientId` by design.
- Updated `docs/designs/authentication/technical.md`'s Cross-App Impact section, which incorrectly stated
  Ultrasonic was unaffected by the Google/Subsonic-credential-forwarding requirement.
- Bumped Ultrasonic's own `versionCode`/`versionName` (`233`/`6.5.3` -> `234`/`6.5.4`).

## [0.0.21] - 2026-07-28

> **Automated the Ultrasonic Android release APK build and publish flow, end to end.** This CI/CD automation already existed in the codebase from earlier work, but had never actually produced a real signed release: the original signing keystore could no longer be located anywhere, so official release APKs were never built by CI before.

### Added
- **Ultrasonic release APK now built and published entirely by CI**: generated a brand-new, dedicated signing keystore (the original could not be recovered) and configured it, together with the `apk-hoster` upload credentials, as GitLab CI/CD variables. `ultrasonic:build-release` now runs automatically on every `release/*` pipeline, builds a signed APK, and uploads it to `https://apk.example.com` alongside `deploy:prod` - no manual local build/upload is needed anymore.
- **Fixed `SIGNING_STORE_FILE` handling**: `scripts/ci/ultrasonic-build-upload.sh` now base64-decodes `SIGNING_STORE_FILE` before use, since GitLab CI/CD variables (even file-type ones) are transmitted as text and can't reliably carry raw binary `.jks` bytes; documented the required `base64 -w0` encoding in `docs/deployment.md`.
- **Clean slate on `apk-hoster`**: removed all previously, manually-published APKs (and their DB records) from `apk-hoster`, since none of them can be validly updated-from once we move to CI-built, newly-signed releases.
- Removed the stale, unusable `services/ultrasonic/ultrasonic-keystore.enc` (an encrypted backup with no known password/decryption method) from the repository.
- **Fixed `ultrasonic:build-release` always failing on `publish.sh`**: `services/ultrasonic/dist` was a machine-specific symlink (`-> /mnt/user/ultrasonic-builds`) that had accidentally been committed to the repository; `mkdir -p dist` fails with `File exists` when `dist` already exists as a (dangling, in CI) symlink, so every CI build of Ultrasonic was doomed to fail at the publish step regardless of signing. Removed the symlink from the repository (`dist/` is already gitignored for local use).
- Bumped Ultrasonic's own `versionCode`/`versionName` (`232`/`6.5.2` -> `233`/`6.5.3`) to mark this as the first official, CI-built and signed release.

### ⚠️ Breaking
- **The Android app's signing key changed.** Anyone who previously installed a manually-built signed release APK (e.g. `v6.5.2-214`) must uninstall it before installing this or any future release, since Android rejects updates signed with a different key and there is no way to keep the old key.

## [0.0.20] - 2026-07-28

> **Continued production log sweep uncovered the `importer_worker` logging the same ~15+ misleading "OS error: check disk space/filesystem" lines on every single import cycle**, for release folders that had actually already been imported successfully before.

### Fixed
- **Importer duplicate folders stuck in `__TODO` forever (`bug 008`)**: `Mover._move_folder()` already handled the "already imported" conflict via `except FileExistsError`, but `shutil.move()` raises `shutil.Error` (not `FileExistsError`) when the destination directory already contains an identically-named entry - this was silently swallowed by the generic `except OSError` branch, mislabeled as a disk/filesystem error, and never cleaned up the duplicate source folder. Now `shutil.Error` is treated identically to `FileExistsError`: the duplicate source is removed so it stops being retried and re-logged as an error on every cycle. Genuine `OSError`s (e.g. actual disk-full) are unaffected.

## [0.0.19] - 2026-07-28

> **Production log sweep uncovered the `telegram_worker` crashing on startup** while loading its `.session` file, and a second, deeper bug that had silently prevented this exact fix from ever reaching production despite a fully green release pipeline.

### Fixed
- **Telegram worker session schema mismatch (`bug 007`)**: `docker/Dockerfile.telegram` ran an unpinned `pip install telethon` in addition to the pinned version from `requirements.txt`, so different rebuilds could install different `telethon` releases. `telethon` changed its session SQLite schema (added a `tmp_auth_key` column) starting with `1.43.0`; an older rebuild could no longer read a `.session` file a newer rebuild had upgraded. Pinned `telethon~=1.44.0` in `requirements.txt` (matching the schema already on disk) and removed the redundant unpinned install so the image always uses a single, reproducible version.
- **`release:build-images` never covered background worker images (`bug 007`)**: `scripts/ci/build-and-push-images.sh` only ever built/pushed `music-manager` and `lms`; `muma-base`, `muma-downloader`, `muma-telegram`, `muma-importer`, and `muma-tools` were never rebuilt or pushed by CI, so `deploy:prod`'s `docker compose pull` kept re-pulling stale, manually-pushed images for every background worker — the telegram fix above went through a fully green `release/*` pipeline including `deploy:prod` without actually reaching production. Extended the script to build and push all five of these images on every `release/*` pipeline.

## [0.0.18] - 2026-07-28

> **The "Artist Images" manager tab was permanently stuck at "0 / 0 artiesten"** with a non-functional search and rescan, even though the artist/image data itself was correctly populated. Root cause: a reverse-proxy routing bug, not a data problem.

### Fixed
- **Artist Images tab always showing 0 / 0 artists (`bug 006`)**: LMS's reverse-proxy `MumaResource.cpp` intercepted every `/api/artists/*` request before it could reach the generic MuMa pass-through proxy, but only correctly implemented two shapes (`.../image` and a plain numeric artist ID for the player's own genre lookup); every other path used by the manager UI (`/images/stats`, `/search`, `/search-all`, `/fetch-progress`, `/{id}/fetch-image`) was rejected with `400 Invalid artist ID` before ever reaching `music-manager`. Narrowed the interception to only those two shapes; everything else now correctly falls through to the generic proxy.

## [0.0.17] - 2026-07-28

> **Fixed a production outage** where every login (username/password and delegated Google auth) crashed with `no such column: u.password_salt`. Root cause: a maintenance sync in `music-manager` dropped the player's real, persistent `user` table (based on an incorrect "it's volatile" assumption), racing with an incomplete fallback table-creation statement in the player itself.

### Fixed
- **`music-manager` LMS DB sync (`bug 005`)**: removed the destructive `DROP TABLE IF EXISTS user, auth_token, ui_state` from `sync_single_server_db()`; `user` is real, persistent state the player reads/writes directly (unlike `auth_token`/`ui_state`, which only ever exist in the player's private in-memory schema and were never actually reachable from this code path anyway).
- **Player schema fallback (`bug 005`)**: `Session::createIndexesIfNeeded()`'s raw-SQL `CREATE TABLE IF NOT EXISTS user` fallback was missing the `password_salt`/`password_hash` legacy columns the ORM mapping requires; added them so this fallback can no longer produce an incompatible schema.
- **Production**: repaired the live database directly (added the missing columns, restarted the player) ahead of this release to restore service immediately; documented in `docs/bug-reports/005-lms-user-table-corruption.md`.

## [0.0.16] - 2026-07-28

> **Fixed artist images not showing in the manager tab (and consequently in the player's Artists view).** Two independent bugs found and fixed: an unauthenticated image request in the manager UI, and a production deployment path mismatch that silently broke the LMS DB sync.

### Fixed
- **Manager tab artist images (`bug 004`)**: `ArtistImagesTab.svelte` requested artist images without any authentication, so every request was rejected with `401 Unauthorized`; the manager's API key is now passed along as an `apiKey` query parameter, matching how other authenticated image requests work.
- **LMS DB sync path mismatch (`bug 004`, production deployment)**: `docker/docker-compose.yml` mounted `music-manager`'s view of the `lms`/`alpha-lms` stacks' native databases (used to sync users/playlists and push artist image references) from a path under this stack's own `HOST_DATA_PATH` that never actually existed on production; it now defaults to the real `lms`/`alpha-lms` stacks' own data directories (`LMS_DATA_PATH`/`ALPHA_LMS_DATA_PATH`, overridable if needed).

## [0.0.15] - 2026-07-28

> **Configured home page "alles tonen" buttons to correctly redirect to their respective tabs with view mode switches.** Release Radar redirects to Release Radar, Songs redirects to songs (with songs view mode active), and Sets redirects to sets (with sets view mode active).

### Changed
- **Home page "alles tonen" buttons (`Dashboard.svelte`)**:
  - **Release Radar**: redirects to the Release Radar tab (`activeView = 'radar'`).
  - **Songs**: sets the view mode to songs and redirects to the songs tab (`viewMode.set('songs'); activeView = 'songs'`).
  - **Sets**: sets the view mode to sets and redirects to the sets tab (`viewMode.set('sets'); activeView = 'sets'`).

## [0.0.14] - 2026-07-28

> **Removed redundant "MuMa Beheer" button from the profile dropdown menu.** Streamlined navigation by relying solely on the persistent sidebar player/management toggle.

### Changed
- **Profile menu (`ProfileButton.svelte`)**: removed the "MuMa Beheer" menu item since system management is already fully accessible via the sidebar header toggle.

## [0.0.13] - 2026-07-28

> **Fixed popular genres statistics semicolon delimiter aggregation and artist image background fetching.** Resolved bug 002 (stats top_genres splitting compound semicolon-delimited genres correctly) and bug 003 (background artist image fetching selecting all missing primary images without image_status filtering bottlenecks).

### Fixed
- **Popular genres semicolon delimiter (`bug 002`)**: updated statistics top-genres aggregation (`stats.py`) to split compound genre strings separated by semicolons (`;` / `,`), trim whitespace, and count individual subgenres accurately.
- **Artist image fetching (`bug 003`)**: updated `run_fetch_missing()` (`artist_images.py`) to process all artists with missing primary images (`primary_image_id IS NULL`) regardless of previous `image_status`, ensuring reliable background and manual fetching of artist images.

## [0.0.12] - 2026-07-28

> **Implemented structured bug reporting workflow and resolved artist image fetch-progress reporting.** Established 2-step bug report markdown files under `docs/bug-reports/` and documented the workflow in `AGENTS.md`.

### Added / Changed
- **Structured Bug Reports (`docs/bug-reports/00#-<title>.md`)**: Added template format (`title`, `status`, `reported problem`, `Possible reason`, `solution`) and updated `AGENTS.md`.
- **Artist Image Fetch Progress**: Ensured progress endpoints handle background fetch statuses cleanly.

## [0.0.9] - 2026-07-28

> **Minor UI cleanups in the sidebar and profile menu.** Removed the legacy UI link, integrated all library sections directly into the main sidebar menu, and removed the redundant "Systeembeheer" item.

### Changed
- **Removed legacy UI button**: removed the "Oude UI (Legacy)" link from the profile dropdown menu in `ProfileButton.svelte`.
- **Consolidated library navigation**: moved all library items (playlists, artists, albums, genres, history, starred) directly into the main sidebar menu in `Sidebar.svelte` with appropriate icons, and removed the separate "JOUW BIBLIOTHEEK" section header.
- **Removed redundant "Systeembeheer" sidebar item**: removed the "Systeembeheer" entry from the sidebar since the play/management toggle in the header already provides this capability.

## [0.0.8] - 2026-07-28

> **Logging out after logging in with Google Auth (or MuMa session) no longer leaves session state behind.** Previously, `handleLogout` only reset `credentials` and cleared `lms_active_view`, leaving `mumaSessionActive`, `mumaApiKey`, `mumaRefreshToken`, `userPermissions`, and `mumaUser` (and their localStorage counterparts) intact. This caused unauthenticated users logging out to remain stuck as 'Gebruiker' with no music access.

### Fixed
- **Thorough logout session cleanup**: `handleLogout` (`ProfileButton.svelte`) now clears all session stores and localStorage entries (`mumaApiKey`, `mumaRefreshToken`, `mumaSessionActive`, `userPermissions`, `mumaUser`) alongside `credentials`, ensuring a clean slate upon logout.

## [0.0.7] - 2026-07-28

> **The login modal was detached into a dedicated full-screen login page, and unauthenticated users are now always redirected there.** Previously, unauthenticated users saw the main music app layout with a floating modal overlay on top; now, logging out or visiting the app without a valid session presents a clean, full-screen dedicated login page (`LoginPage.svelte`) at `/login` and redirects all non-authenticated navigation there.

### Added / Changed
- **Dedicated full-screen login page**: refactored `AuthOverlay.svelte` into `LoginPage.svelte` (`services/frontend/src/lib/LoginPage.svelte`), removing the floating modal overlay.
- **Mandatory login redirection**: `App.svelte` now strictly checks session state (`!$credentials.username && !$mumaSessionActive`), rendering the login page and enforcing URL redirection to `/login` whenever the user is not logged in.

## [0.0.6] - 2026-07-27

> **A Google-authenticated user was logged in as "Gebruiker" and could not see any music.** Google
> Sign-In correctly authenticated against `music-manager` (permissions, admin badge, etc.), but the
> frontend's `credentials` (username/password) store -- which every Subsonic call (`getGenres`,
> albums, streaming, ...) and the profile display name are derived from -- was never populated after
> a Google login, since a Google sign-in never learns the account's real password.

### Fixed
- **Google-signed-in users saw "Gebruiker" and no music at all (`getGenres` failing with "Required
  parameter 'c' is missing")**: `AuthOverlay.svelte`'s `handleGoogleResponse` only ever set
  `mumaUser`/`userPermissions`/`mumaApiKey`, never the `credentials` store that `authParams`
  (and therefore every Subsonic/LMS REST call across the app) and `ProfileButton`'s displayed
  username are derived from -- so a Google-authenticated session had no way to actually talk to
  Subsonic at all. `POST /api/auth/login` now also accepts a user's own `api_key` as a valid
  `password` (in addition to the real, bcrypt-hashed password), and `handleGoogleResponse` uses
  that to populate `credentials` with `{username: user.username, password: api_key}` right after a
  successful Google login -- restoring the user's real username in the UI and making all Subsonic
  calls (and, through LMS's `MusicManagementPasswordService`, Subsonic streaming itself) work
  exactly the same regardless of which login method was used, per the linked-account requirement
  from 0.0.3/0.0.5.

## [0.0.5] - 2026-07-27

> **The "Sign in with Google" button disappeared from production again, and the server would have
> silently accepted a Google ID token from ANY Google OAuth client, not just ours.** Root cause: the
> `GOOGLE_CLIENT_ID` (backend) and `VITE_GOOGLE_CLIENT_ID` (frontend build-arg) CI/CD variables were never
> actually populated in `PROD_ENV_FILE`/`PROD_ENV_FILE_LMS` -- they were only ever set directly on the
> production host, outside of the CI/CD pipeline, so the first CI-driven rebuild after 0.0.2 wiped them out.

### Fixed
- **Google Sign-In button missing in production, username/password-only login shown**: `VITE_GOOGLE_CLIENT_ID`
  was empty when the `lms` image's frontend bundle was built by `release:build-images`, so Vite's dead-code
  elimination stripped the entire `if (GOOGLE_CLIENT_ID) { ... }` branch in `AuthOverlay.svelte` (including
  the Google Identity Services script load and the `#googleBtn` render call) out of the production bundle.
  The `PROD_ENV_FILE_LMS` CI/CD variable now includes `VITE_GOOGLE_CLIENT_ID`, matching the value already
  configured directly on Google Cloud Console for this app.
- **Google login would have silently accepted a token issued for a *different* Google OAuth client**:
  `GOOGLE_CLIENT_ID` was empty for the same reason, and `google.oauth2.id_token.verify_oauth2_token()`
  silently skips its `aud` (audience) check entirely when `audience=None` -- so the backend was verifying
  only the token's signature and issuer, not that it was actually issued for *our* app.
  `_verify_google_id_token()` (`services/music_manager/routers/user_requests.py`) now raises a `500` with a
  clear message instead of degrading into that unauthenticated-by-omission state, and `PROD_ENV_FILE` now
  includes `GOOGLE_CLIENT_ID` too.
- Both username/password (Subsonic) login and Google Sign-In already resolved to the exact same underlying
  `User` row (see 0.0.3's "Merge duplicate user accounts" / "Link a Google access request to an existing
  account"); this fix restores that both methods are actually *available* on the login screen again, with
  identical resulting permissions/session regardless of which one was used.
- **The LMS `/api/...` proxy (`MumaResource`) collapsed every non-`200` response from MuMa into a generic
  `502 Bad Gateway`**, discarding the real status code and error body MuMa returned (e.g. `401 Invalid
  username or password`, `404 Track not found`). Root cause: `core::http::SendQueue` only ever invoked
  `onSuccessFunc` for a `200` response and routed everything else through `onFailureFunc` (which every proxy
  call in `MumaResource` hard-codes to `502`) — appropriate for the client's other, non-proxy callers (which
  only care "worked" vs. "didn't"), but wrong for a reverse proxy, where the exact upstream status/body must
  reach the original caller. Added an opt-in `ClientRequestParameters::treatAnyStatusAsSuccess` flag (default
  `false`, so every existing caller is unaffected) and set it on all of `MumaResource`'s raw pass-through
  proxy calls (generic `/api/*` GET/POST/PUT/DELETE, artist image, track refresh, per-app user settings).
- **Added a `release:check-secrets` CI job** (`scripts/ci/check-required-secrets.sh`) that fails a
  `release/*` pipeline immediately, before any image is built, if `GOOGLE_CLIENT_ID`
  (`PROD_ENV_FILE`) or `VITE_GOOGLE_CLIENT_ID` (`PROD_ENV_FILE_LMS`) is missing or empty — the actual root
  cause of the button disappearing again was an unrelated edit to one of those CI/CD variables silently
  dropping this key, with nothing in the pipeline noticing. See `docs/deployment.md` and `AGENTS.md`
  ("Testing & Stability") for the policy: this job's pass/fail result is a hard requirement for a release,
  the same as any other check in this list, even though GitLab itself has no way to enforce it structurally.

## [0.0.4] - 2026-07-27

### Fixed
- **A successful Google login could still show "Kon geen verbinding maken met de Google login API"**:
  `POST /api/auth/google` (and `/api/auth/login`, `/api/auth/refresh`) returned the account fields spread
  directly onto the top-level response object instead of nested under a `user` key, while
  `AuthOverlay.svelte` (and every other frontend caller) reads `data.user.permissions`/`data.user` — matching
  what `/api/auth/verify` already returns. That mismatch made `data.user` `undefined`, throwing inside the
  `try` block right after a `200 OK` response and landing in the generic connection-error `catch`, even
  though the login itself had actually succeeded server-side (the user was left stuck on the login screen
  despite the account being valid and linked). `login`, `refresh_access_token`
  (`services/music_manager/routers/users.py`) and `google_login`
  (`services/music_manager/routers/user_requests.py`) now all return `{status: "ok", user: {...}, api_key,
  access_token, refresh_token}`, matching the documented contract in
  `docs/designs/authentication/technical.md`.
- **Google Sign-In popup could silently fail with "Cross-Origin-Opener-Policy policy would block the
  window.postMessage call."**: no response served by the LMS reverse proxy set a `Cross-Origin-Opener-Policy`
  header at all, which some browsers treat as reason to sever the window reference to Google's Sign-In
  popup, breaking the postMessage-based token hand-off back to `AuthOverlay.svelte` before the ID token
  ever reaches `/api/auth/google`. `services/music-management-server/nginx/reverse-proxy.conf` now sends
  `Cross-Origin-Opener-Policy: same-origin-allow-popups`, which keeps same-origin window isolation while
  explicitly allowing the trusted Google popup to keep talking back to the page.

## [0.0.3] - 2026-07-26

> **Google Sign-In is now fully wired up end-to-end: the button actually renders, the login it produces
> actually works, and duplicate accounts can be cleaned up.** The frontend/backend code for "Sign in with
> Google" already existed, but the `VITE_GOOGLE_CLIENT_ID` build-arg was never passed to any of the three
> places that build the `lms` image (so the button never rendered), the LMS proxy layer blocked the
> Google auth endpoints and swapped every caller's identity for a generic one (so logins that did render
> failed with `401` and admins lost their management buttons), and there was no way to merge an account
> created via a Google access request into an already-existing local/Subsonic account for the same person.

### Added
- **Google Sign-In build wiring**: `build.sh`, `services/music-management-server/scripts/build.sh`, and
  `scripts/ci/build-and-push-images.sh` now all pass `--build-arg VITE_GOOGLE_CLIENT_ID=...` when building
  the `lms` image, sourced from a new `VITE_GOOGLE_CLIENT_ID` entry in
  `services/music-management-server/.env` (mirroring the backend's existing `GOOGLE_CLIENT_ID`). Documented
  in a new "Google Sign-In setup" subsection of `docs/deployment.md`.
- **Merge duplicate user accounts**: new `POST /api/users/{id}/merge` endpoint (permission `users.merge`)
  moves everything owned by a secondary account (login identities, sessions, dynamic playlists, per-app
  settings, ListenBrainz link, ratings and scrobble history) onto the primary account and then deletes the
  secondary account. Conflicts on a shared unique key are resolved by keeping the primary account's
  existing data. Exposed in the "Beheer" tab as an "Accounts samenvoegen" panel.
- **Link a Google access request to an existing account**: approving a pending access request
  (`POST /api/user-requests/{id}/approve`) now accepts an optional `link_user_id`, which links the Google
  identity to that account instead of always creating a brand-new one — preventing this kind of duplicate
  from happening again.

### Fixed
- **`/api/auth/google` / `/api/auth/access-request` / `/api/auth/setup*` were never reachable**: the LMS
  proxy (`MumaResource::handleRequest`) required an already-authenticated caller for every endpoint, which
  made it impossible for a brand-new Google identity (which by definition has no credentials yet) to ever
  call the very endpoints meant to grant it access. These are now explicitly treated as public,
  unauthenticated pass-throughs, exactly like the existing `/api/auth/login`.
- **Caller identity was discarded on every proxied request**: `MumaResource` always forwarded the
  server-wide `MUSIC_MANAGEMENT_API_KEY` to MuMa instead of the caller's own `X-API-Key`, so MuMa saw every
  request (Subsonic or Google-authenticated) as a generic, permission-less "system" caller rather than the
  actual logged-in user. The caller's own key is now forwarded first, falling back to the system key only
  when the caller didn't send one.
- **Frontend never recognized the "system" identity as an admin**: because Subsonic admins authenticate via
  the shared system key (which MuMa itself always grants full access to), the "Beheer" tab's
  `hasPermission()` checks (gating "add user", "delete user", role changes, ...) always evaluated to
  `false` for them, hiding those actions even for a real admin. The frontend now mirrors MuMa's own "system
  key = full access" rule.
- **`isAdmin` never accounted for a Google-authenticated admin's RBAC role**, and was never refreshed from
  a persisted session after a page reload — both are now covered so the "Beheer" nav entry and page gating
  work the same regardless of login method.
- **Deleting a user could fail with a generic, unhelpful error**: `DELETE /api/users/{id}` now explicitly
  cleans up dependent rows (login identities, sessions, dynamic playlists, per-app settings, ListenBrainz
  link) before deleting the account, protects the last remaining admin account from being deleted, and
  returns a clear `Verwijderen mislukt: ...` message instead of a bare `500` on failure.
- **Delete-user button visibility check used the wrong permission**: the "Beheer" tab's delete button was
  gated on `users.create` instead of `users.update`, which no longer matched what the backend actually
  requires.

### Notes
- A separate, lower-severity issue was found but intentionally **not** fixed here: the shared HTTP client
  used by `MumaResource` (`core::http::SendQueue`) treats any non-2xx response from MuMa as a transport
  failure, collapsing it into a generic `502 Bad Gateway` instead of relaying the real status code/body.
  This doesn't block real logins (a valid Google token returns `200`), but it does hide legitimate error
  details (e.g. an actually-invalid token, or a `403`) behind a generic gateway error. Fixing it would
  touch a shared component used by every other `IClient` consumer in the codebase, so it's flagged here as
  a follow-up rather than changed as part of this fix.

## [0.0.2] - 2026-07-26

> **Fix: production was deploying stale images.** After cutting `0.0.1`, `music.example.com`
> kept showing old behavior post-deploy. Root cause: `deploy:prod` only ever ran
> `docker compose pull`, but nothing in the pipeline actually *built and pushed* fresh
> `music-manager`/`lms` images first — it silently kept re-pulling whatever image had last been
> pushed **manually**, so a release could "deploy successfully" while production kept running old
> code.

### Fixed
- **Missing image build/publish step in the release pipeline**: added a new `release:build-images`
  CI job (stage `release`, before `deploy`) that builds and pushes fresh `music-manager` and `lms`
  (`music-management-server`) Docker images to Docker Hub on every `release/*` branch, via the new
  `scripts/ci/build-and-push-images.sh`. `deploy:prod` now always pulls an image that was just built
  from the code actually being released, instead of a possibly-stale, manually-pushed one.
- `release:build-images` is gated on the new `DOCKERHUB_USERNAME`/`DOCKERHUB_TOKEN` CI/CD variables
  and runs in the same `release` stage as `release:version-check`, so `deploy:prod` (stage `deploy`)
  cannot start until both have succeeded — a failed or skipped image build blocks the deploy.

## [0.0.1] - 2026-07-26

> **Version reset.** This release intentionally restarts the overarching monorepo version number at
> `0.0.1`, replacing the previous `2.x` line. It marks the first official release produced under the
> new `develop` → `release/*` → `master` branching/release-management flow described in
> `docs/release-management.md`, and the first release of this project as a single, unified monorepo
> (backend services + Music Management Server + frontend + Ultrasonic client, one shared history). The
> root `VERSION` is the *overarching* version for this monorepo release line; individual components
> (e.g. Ultrasonic's own `versionName`/`versionCode`) keep their own, independent version numbers, as
> documented in the versioning policy.

### Added
- **Unified release process**: introduced the `develop` (integration) → `release/x.y.z` (stabilization +
  production deploy) → `master` (tagged, append-only production record) branch model. Production deploys
  now only happen from `release/*` branches, gated by an automated `release:version-check` that fails the
  pipeline if `VERSION`, `CHANGELOG.md`, or `RELEASE_NOTES.md` weren't updated. See
  `docs/release-management.md` for the full design and rationale.
- **CI-driven git tagging**: merges into `master` now automatically create an immutable `release-vX.Y.Z`
  tag (and `ultrasonic-vX.Y.Z` when an Ultrasonic release is included), so "what's actually live" can
  always be answered from `master`'s tag history, with no manual `git tag` step.
- **Automated Ultrasonic APK distribution**: CI now automatically builds and uploads a debug Ultrasonic
  APK to `apk-hoster` on every `develop` merge, and the official, signed APK on every `release/*` branch
  (previously both were fully manual, local-only steps).

### Changed
- **Repository**: merged the previously split-out `music-management-server` (LMS) and `ultrasonic`
  Android app repositories directly into this repository as a single monorepo, with their full commit
  history preserved (via `git subtree`). The `frontend` (which never had its own separate history) is
  now tracked here too. There are no more submodules or separate gitlab remotes for these projects —
  see `AGENTS.md` for the rationale (solo developer, tightly-coupled apps, one shared history).
- **Production deployment**: the `deploy:prod` pipeline job was fixed to use dedicated, CI-managed SSH
  key authentication and now reliably deploys both production stacks (`music-management` and `lms`)
  idempotently from a `release/*` branch, instead of the previously broken/manual `main`/`develop` flow.

## [2.6.0] - 2026-07-20

### Added
- **Mobile Integration (Ultrasonic)**: Formalized the integration of the Ultrasonic Android app into the ecosystem documentation.
- **Client Settings Sync**: Enabled server-side backup and synchronization for mobile application settings via the Music Manager API.
- **Subsonic API Support**: Standardized Subsonic API responses in the Music Management Server for seamless compatibility with mobile clients.
- **APK Distribution**: Integrated `apk-hoster` for independent distribution of mobile updates.

## [2.5.0] - 2026-07-11

### Changed
- **Path Migration**: Migrated the entire application from `/music` to `/mnt/music` across Docker configurations, environment variables, and application logic.
- **API Architecture**: Centralized `common/api` into `music-manager`. Workers now push updates to the `music-manager` hub instead of running their own API servers, simplifying the architecture.
- **Project Structure**: Removed the intermediate `music-management/` folder and moved `services/` to the root, resulting in a cleaner layout and simplified `PYTHONPATH`.
- **Worker Integration**: Fully integrated YouTube and SoundCloud downloaders with the centralized `job_manager` for real-time progress tracking.

### Added
- **Test Isolation**: Introduced `services/conftest.py` for aggressive mocking of heavy dependencies (`pymysql`, `mutagen`, `yt-dlp`), enabling tests to run without a live database.

### Fixed
- **API Routing**: Fixed path mismatches in tests and standardized all API routes under the `/api` prefix in `music-manager`.
- **Code Quality**: Removed over 80 redundant proxy methods in `management.py` and improved robustness of `Tag.to_string` and path resolution logic.

## [2.4.1] - 2026-07-10

### Added
- **Redownload Feature**: Added a "Redownload" button to the Library UI for SoundCloud and YouTube tracks.
- **Archive Integration**: The system now automatically finds the original source URL from the download archives to facilitate redownloads.
- **Downloader Enhancements**: Added `redownload_mode` to SoundCloud and YouTube downloaders to allow bypassing existing archive entries when explicitly requested.

## [2.4.0] - 2026-07-10

### Changed
- **Architecture**: Integrated the `tagger` and `scanner` services directly into the `music-manager` service.
- **Workflow**: Tagger and Scanner now run as background threads within the music manager process, reducing inter-service communication overhead and simplifying Docker deployment.
- **API**: Moved `/tag/*` and `/scan/*` endpoints to `/api/tagger/*` and `/api/scanner/*` respectively within the music manager API.
- **Performance**: Track rescan in the library now uses direct function calls for tagging and scanning instead of internal HTTP requests.

## [2.3.4] - 2026-07-10

### Fixed
- **Rescan Workflow**: Fixed a race condition where the scanner would run before the tagger finished by making single-file API calls synchronous.
- **Tagger Metadata**: Fixed an issue where manual rescans wouldn't clear the `needs_rescan` flag in the database.
- **Docker Networking**: Corrected internal service URLs in `docker-compose.yml` to use internal container ports instead of host-mapped ports.

## [2.3.3] - 2026-07-10

### Added
- **Scanner Service API**: Integrated a FastAPI-based REST API on port 8002 for the scanner service.
- **Immediate DB Sync**: Library track rescan now triggers both the tagger and the scanner for instant database updates.

## [2.3.2] - 2026-07-10

### Added
- **Tagger Service API**: Integrated a FastAPI-based REST API on port 8001 for the tagger service.
- **On-Startup Full Scan**: Service now explicitly performs a full tagging scan immediately upon startup.
- **Tagging Control Endpoints**: New `/tag/all` and `/tag/file` endpoints to trigger metadata enforcement via API.

## [2.3.1] - 2026-07-10

### Added
- **Tagger Auto-Detection**: New `TagSingleFile(path)` utility function that automatically determines the song source (SoundCloud, YouTube, Label, etc.) based on its file location and applies the appropriate tagging rules.

## [2.3.0] - 2026-07-05

### Added
- **MuMa Cloud Sync**: New server-side backup system for application settings (User App Settings API).
- **Settings API**: Endpoints for saving and retrieving JSON-based application configurations per user and app ID.
- **Enhanced Scrobble Imports**: Implemented robust pagination for ListenBrainz imports, allowing retrieval of up to 10,000 tracks.
- **Artist Image Synchronization**: Centralized artwork management for multi-LMS environments (Stable and Alpha).
- **Consolidated Versioning**: Unified version reporting for all internal worker services in the dashboard.

### Changed
- **Authentication**: Streamlined API key flow; keys returned at login are now universally valid for user-specific actions.
- **Security**: Removed sensitive API key displays from the frontend, relying on session-based auth.
- **Database Architecture**: Added `user_app_settings` and `scrobble_imports` tables to core initialization.
- **Stats Engine**: Refactored statistics queries to provide more accurate match rates and genre distributions.

## [2.2.0] - 2026-07-05

### Added
- **Dynamic Playlists**: Support for storing and managing dynamic playlist definitions (modifiers) in the database.
- **Management API**: New endpoints to create, update, and retrieve dynamic playlists.
- **User Service**: Added dynamic playlist management to the user-centric API.
- **LMS Integration**: Added a feedback hook to receive and process real-time playlist updates from LMS.

## [2.1.35] - 2026-07-05
### Fixed
- **User Management**: Fixed an issue where deleting or creating users in MuMa did not reflect in LMS due to a read-only database mount.
- **Service Integration**: Changed the `lms.db` mount in `user-service` to read-write by mounting the parent directory, allowing SQLite to handle journal files.
- **Logging**: Added enhanced logging and permission checks in the User Service to monitor LMS database connectivity.

## [2.1.34] - 2026-07-05
### Added
- **User Management**: Added ability to delete users and set default passwords in the Control Center.
- **LMS Synchronization**: Implemented immediate bidirectional synchronization with the Lightweight Music Server (LMS) database.

## [2.1.33] - 2026-07-05
### Fixed
- **Stats Service**: Resolved build and deployment issues for the new stats microservice.
- **Database**: Cleaned up redundant indices on the `rules_genres` table.

## [2.1.32] - 2026-07-05
### Added
- **Stats Microservice**: Decoupled library statistics into a dedicated microservice (`stats-service`).
- **Improved Management API**: Integrated statistics module directly into the Control Center via proxy to the new microservice.
- **Library Stats CLI**: Added a `stats` command to `install.sh` to quickly view library statistics from the terminal.

## [2.1.31] - 2026-07-05
### Added
- **Health & Activity Dashboard**: New tab in the Control Center for real-time monitoring of Docker containers.
- **Docker Logs Viewer**: View the logs of all Muma-related containers directly from the UI.
- **Recent Activity**: Overview of recently added and tagged tracks, categorized by source (YouTube, SoundCloud, etc.).

## [2.1.30] - 2026-07-05
### Added
- **LMS Subsonic API Key**: The Subsonic API key in LMS can now be configured via the environment variable `LMS_SUBSONIC_API_KEY`, facilitating integration with external apps.

## [2.1.29] - 2026-07-05
### Added
- **Centralized Authentication**: Introduced a centralized `/auth/verify` endpoint in the User Service to validate both system-wide and user-specific API keys.
- **Enhanced Security**: Repurposed the `user-service` as an Identity Provider, allowing services to offload credential verification.

### Fixed
- **Network Hardening**: Minimized the attack surface by removing public port exposures for internal services (Rating, Scrobble, User) in Docker Compose.
- **Internal Communication**: Optimized service-to-service communication by using the shared `music-management_db` Docker network and internal DNS.

## [2.1.28] - 2026-07-04
### Fixed
- **Infrastructure**: Added `LMS_SUBSONIC_API_KEY` to the main `docker-compose.yml` for correct propagation to the User Service.

## [2.1.27] - 2026-07-04
### Fixed
- **LMS Sync**: Resolved mismatch in API keys. Now uses a specific `LMS_SUBSONIC_API_KEY` for LMS, while the Muma services retain their own key.
- **Service Stability**: Improved error handling in the User Service for LMS sync responses.

## [2.1.26] - 2026-07-04
### Fixed
- **LMS Sync**: Resolved authentication issue with the LMS Subsonic API by explicitly adding the `apiKey` parameter to the sync URL.

## [2.1.25] - 2026-07-04
### Fixed
- **API Security**: Resolved inconsistencies in API keys between microservices and the Control Center in Docker Compose configurations.
- **LMS Sync**: Confirmed that the `user-service` sends the correct `X-API-Key` to LMS during user synchronization.

## [2.1.24] - 2026-07-04
### Added
- **YouTube Management**: YouTube accounts can now be managed via the Control Center.
- **Cookie Support**: Added support for Firefox cookies from a shared Docker volume for both YouTube and SoundCloud downloaders.

### Fixed
- **UI Consistency**: SoundCloud and YouTube management pages are now consistent and support removing accounts.

## [2.1.23] - 2026-07-04
### Fixed
- **User Service**: Fixed syntax and logic errors in LMS synchronization (`run_lms_sync`).
- **Configuration**: Added `LMS_HOSTS` support for multiple LMS instances and fixed `LMS_HOST` typo in `.env`.

## [2.1.22] - 2026-07-04
### Added
- **API Security**: Implemented system-wide API key validation (`X-API-Key`) for all microservices.
- **Control Center**: Added ability to set and save the API key in the dashboard.
- **User Service**: Added `user-service` to the `full` Docker Compose configuration.

### Fixed
- **API Consistency**: The `API_KEY` is now synchronized across all modules in the `music-manager`.
- **LMS Configuration**: Corrected default LMS host to `lms.example.com`.

## [2.1.20] - 2026-07-04
### Fixed
- **LMS Configuration**: Corrected default LMS host to `lms.example.com` and updated CORS origins to the correct production IP (192.0.2.27).

## [2.1.19] - 2026-07-04
### Added
- **User Password Management**: Set passwords via Control Center with automatic synchronization to LMS.
- **Security**: Implemented Bcrypt hashing for secure storage of user passwords.

## [2.1.18] - 2026-07-04
### Added
- **User Migration**: Imported users from `lms.db` to the User Service.
- **LMS Integration**: Added support for direct SQLite database synchronization from LMS.
- **UI Enhancements**: Added new synchronization options to the Users dashboard.

## [2.1.17] - 2026-07-04
### Added
- **User Service**: New microservice for centralized user management and external account links (ListenBrainz).
- **Control Center**: New "Users" dashboard for managing users and their API keys.
- **LMS Sync**: Ability to synchronize users/players directly from Logitech Media Server.
- **Scrobble Integration**: Integrated ListenBrainz imports based on saved user profiles.

## [2.1.16] - 2026-07-04
### Fixed
- **Scrobble Service**: Fixed ListenBrainz import crash caused by missing `json` import and improper data serialization.
- **Scrobble Service**: Added required `User-Agent` header to ListenBrainz API requests to prevent blocking.
- **Scrobble Service**: Improved database error handling during background import tasks.

## [2.1.15] - 2026-07-04
### Added
- **Control Center**: New Scrobble Service dashboard with ListenBrainz import monitoring.
- **Scrobble Service**: Added `scrobble_imports` table for tracking background task progress.
- **Scrobble Service**: New endpoints for polling import status and fetching recent history.
- **Frontend**: Real-time polling for active imports and visual progress bars.

## [2.1.14] - 2026-07-04
### Added
- **Scrobble Service**: New microservice for tracking listens and importing history from ListenBrainz.
- **ListenBrainz Integration**: Support for importing user listening history and automatic track matching.
- **Smart Matching**: Fallback logic for matching tracks via Artist/Title when MBIDs are unavailable.
- **Infrastructure**: Added Scrobble Service to the build pipeline and Control Center dashboard.

## [2.1.13] - 2026-07-04
### Changed
- **Rating System**: Renamed database table from `track_ratings` to `rating_tracks` for better consistency.
- **UI Refinement**: Global override of focus rings to eliminate blue browser defaults in favor of Spotify Green.
- **Styling**: Further alignment with `styleguide.md` for a consistent dark theme experience.

## [2.1.12] - 2026-07-04
### Added
- **Debug Support**: Added `--debug` flag to `build.sh` and `publish.sh` for detailed execution logging.
- **Design System**: Created `styleguide.md` to formalize the Spotify-inspired dark theme (Green/Black/Gray).
- **UI Refinement**: Standardized all UI accent colors to Spotify Green (`#1DB954`) and improved focus/selection states.

## [2.1.11] - 2026-07-04
### Added
- **Centralized Release Notes**: The Control Center now aggregates and displays release notes and changelogs from all modular services.
- **Service API Expansion**: Added versioning and release notes endpoints to the Rating System service.

## [2.1.11] - 2026-07-05
### Added
- **Library Stats CLI**: Added a `stats` command to `install.sh` to quickly view library statistics from the terminal.
- **Improved Management API**: Integrated statistics module directly into the Control Center.

## [2.1.10] - 2026-07-04
### Added
- **Modular Containerization**: Split the monolithic application into 10 specialized, lightweight services (`muma-scanner`, `muma-tagger`, `muma-downloader`, etc.).
- **Smart Build System**: Introduced `scripts/affected.sh` and optimized `install.sh` to skip builds for unedited modules.
- **Unified Base Image**: Created `muma-base` to share core music logic and dependencies, reducing image size and ensuring consistency.
- **Parallel Builds**: Optimized `build.sh` and `publish.sh` to execute Docker operations in parallel.

### Fixed
- Fixed missing `pymysql` and other dependencies in `ml-analyzer` worker.
- Silenced database permission warnings in workers when tables/views are already managed by migrations.
- Improved Telegram worker stability with dedicated `asyncio` loop management.
- Resolved circular dependencies by consolidating core logic in the base image.

## [2.1.9] - 2026-07-04
### Fixed
- Fixed `ml-analyzer` being offline by setting up a repeat loop and proper Docker command.
- Resolved `RuntimeError` in Telegram worker by improving `asyncio` loop management and explicitly passing it to Telethon.
- Removed redundant `yt-dlp` updates on service startup to speed up container initialization.

## [2.1.8] - 2026-07-04
### Fixed
- Improved Telegram worker stability by using a dedicated event loop and modern `asyncio` patterns.

## [2.1.7] - 2026-07-04
### Fixed
- Fixed `KeyError` in YouTube downloader by aligning configuration keys with `ConfigStore`.
- Added missing `muma-rating-system` to build and deployment scripts.

## [2.1.6] - 2026-07-04
### Fixed
- Consolidated all service code into the base image to resolve circular and cross-service dependencies.
- Added all common dependencies (`yt-dlp`, `telethon`, `patool`, etc.) to the base image to ensure all workers can share the same entry points.

## [2.1.5] - 2026-07-04
### Fixed
- Fixed API server crash due to missing dependencies (`markdown`, `pydantic`) in worker images.
- Fixed `UnboundLocalError` in API initialization.
- Fixed package recognition for `services.tagger` in modular workers by including `__init__.py` in the base image.

## [2.1.4] - 2026-07-04
### Fixed
- Fixed missing `requests` dependency in Management API.
- Fixed `ModuleNotFoundError` in modular worker images by moving core music logic (`BaseSong`, etc.) to the base image.
- Improved Management API Dockerfile to inherit from the shared base image.

## [2.1.3] - 2026-07-04
### Changed
- **Consolidated Deployment**: Unified root `deploy.sh` and `scripts/deploy-stack.sh` into a single `scripts/deploy.sh`.
- **Streamlined Workflow**: Updated `install.sh` to use the new centralized deployment script.

## [2.1.2] - 2026-07-04
### Fixed
- Fixed SQL syntax errors in `migrate_v2.sql` for MariaDB compatibility.
- Unified artist and label genre rule tables into a normalized structure with backward-compatible views.
- Improved database initialization logic to handle table renames and view creation.

## [2.1.1] - 2026-07-04
### Added
- Formalized `scanner_service` in Docker Compose configurations for production deployment.
- Created `docker-compose.full.yml` as a consolidated configuration for Portainer and manual stack management.

## [2.1.0] - 2026-07-04

### Added
- **Artist-Genre Editor**: A new Spotify-inspired UI for mapping artists and labels to genres.
- **Library Scanner**: A new `muma-library-scanner` service that automatically indexes audio files into the database.
- **ReadonlySong**: A specialized song class for metadata extraction without file modification.
- **Database Schema v3**: Added tables for `rules_artist_genres`, `rules_label_genres`, `library_artists`, and `library_labels`.
- **API Endpoints**: New REST endpoints for artists, labels, and genre-mapping rules.

### Fixed
- Improved database connection reliability in the Management API.
- Standardized Docker worker configurations.

## [2.0.0] - 2026-07-04
### Added
- Created `scripts/deploy-stack.sh`, a generalized Docker stack deployment tool supporting Portainer discovery, SSH transfer, and intelligent fallbacks.
- Support for initial stack creation: the deployment script now automatically creates the stack if it does not exist yet using a local template.
- Modular build system with separate `build.sh`, `publish.sh`, and `deploy.sh` scripts.
- Versioned Docker tagging: images are now tagged with both `:latest` and the repository version (e.g., `:2.0.0`).
- Portainer Webhook support for automated Stack updates.
- Automatic Docker group permission handling via `sg docker` re-execution.
- Standardized `.env` configuration for all deployment targets.
- `install.sh` shortcut for the full build-publish-deploy pipeline.
- Proactive Docker registry authentication checks.
- Advanced audio feature extraction (MFCC, ZCR, Rolloff, Chroma) in ML analyzer.

### Changed
- **Deployment**: Refactored `deploy.sh` to use the new generalized `deploy-stack.sh` helper, simplifying per-project deployment scripts.
- **Deployment**: Enhanced stack discovery to support `PORTAINER_HOST` for pulling master templates.
- **Deployment**: Improved robustness with `base64` template transfer and automated tab-to-space conversion in compose files.
- Refactored core to use normalized database schema v2.
- Updated `install.sh` to automate environment setup and dependency installation.
- Optimized Docker builds by using system FFmpeg packages instead of source builds.
- Unified deployment variables across repositories.

### Fixed
- Fixed Docker Hub push denial by adding pre-flight authentication checks.
- Fixed path typos in configuration store and downloader modules.
- Improved database storage robustness for high-load analysis jobs.
