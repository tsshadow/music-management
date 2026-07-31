# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
- **Release builds crashed with `IllegalArgumentException: class com.google.common.reflect.TypeCapture
  isn't parameterized` whenever a track's genre list was deserialized**: the Room `Converters`, the
  `MediaItem.toTrack()` converter and `TileStorage` built their Gson type via an anonymous Guava
  `TypeToken` subclass. Guava ships no consumer ProGuard rules, so with
  `android.enableR8.fullMode=true` R8 merged away the parameterized superclass those tokens read at
  runtime. This fired on `onTimelineChanged`/`onMediaItemTransition`, i.e. on nearly every playback
  start, and only in release builds — it accounts for 15 of the 16 crashes collected on 6.5.14
  through 6.5.18. All three sites now deserialize through `Array<T>::class.java`, which needs no
  runtime generic signature. Keep rules for the Guava `TypeToken` hierarchy were added as a second
  line of defence. The Gson `TypeToken` usages elsewhere are unaffected: Gson ships its own consumer
  rules.
- **Errors reported while no Activity was available took the whole app down**: `InfoDialog`/
  `ErrorDialog` built their `MaterialAlertDialogBuilder` in the constructor, outside the existing
  try/catch, so a non-AppCompat context — such as the application context handed to a background
  coroutine's error handler — threw "The style on this component requires your app theme to be
  Theme.AppCompat". The builder is now created lazily against a themed context, and falls back to a
  toast if the dialog still cannot be shown.
- **An exception thrown inside any RxBus subscriber killed the process**: none of the subscribers
  pass an `onError` handler, so RxJava rethrew as `OnErrorNotImplementedException` on the delivering
  thread. A global `RxJavaPlugins` error handler now logs these instead.
- **Android Auto bleef hangen op een dode of offline serververbinding.** De mediasessie van Auto
  haalde de `MusicService` één keer op, bij het aanmaken van de sessie, en hield die instantie vast
  zolang de app draaide. Alles wat die instantie vervangt — van server wisselen, inloggegevens
  aanpassen, of `getMusicService()` die de offline service teruggeeft terwijl de server onbereikbaar
  is — liet Auto met de oude achter: de mappenstructuur werd nog gewoon getoond, maar elke lijst
  kwam leeg terug, ook nadat de app op de telefoon (die per aanroep opnieuw ophaalt) allang weer
  werkte. Auto haalt de service nu bij elke aanroep opnieuw op.

## [6.5.12] - 2026-07-30

### Added
- **Welcome dialog now distinguishes "server unreachable" from "login failed"**: both the manual
  username/password submit and "Sign in with Google" previously collapsed every failure into the
  same generic network-error message. Added an unauthenticated `/rest/ping.view` reachability
  probe that runs on login failure to tell the two apart.

### Fixed
- **The welcome dialog's login test could report success without ever contacting the server**:
  when "Auto-switch server online/offline" was enabled (the default before 6.5.11/version 0.0.34)
  and a `ConnectivityManager` capability check transiently/incorrectly reported no network, the
  login test silently used the no-op `OfflineMusicService.ping()` instead of actually validating
  the server/credentials. The login test now always uses the real, network-backed service.

## [6.5.11] - 2026-07-29

### Changed
- **Dependencies**: Updated `activity-ktx`, `core-ktx`, `gson`, `okhttp`, `rxjava`, and other core libraries to latest stable versions.
- **Target SDK**: Updated to Android 17 (API 37).
- **Login/auth UI**: Restyled the login/welcome dialog, edit-server screen, and Google
  access-request screen to match the web frontend: filled pill-shaped inputs, a real "Sign in with
  Google" button with the brand G logo, a proper divider, a red error banner, and colored
  info/success/error status banners for pending/rejected/approved access requests. Replaced a
  stray non-brand color in the filter dialog/search FAB with `spotify_green`, and aligned the nav
  drawer's item tinting with the bottom nav's brand colors.
- **Settings**: `autoSwitchOffline` now defaults to `false` instead of `true`.

### Added
- **Export to Media Device**: New feature to export the current playlist to external USB devices (e.g., Shokz OpenSwim Pro) via SAF. Includes an option to clear the destination folder before exporting.

## [6.5.2-232] - 2026-07-16

### Fixed
- **Update Checker**: Added `u=guest` and `p=guest` credentials to APK download URL to prevent access errors.

## [6.5.0] - 2026-07-11

### Added
- **Log Viewer**: New diagnostic tool accessible from Settings > About to view and share app logs.
- **Architecture Tests**: Integrated ArchUnit for maintaining code structure and dependency rules.
- **Coverage Reporting**: Added JaCoCo integration for automated test coverage analysis.
- **Welcome Messages**: Dynamic greeting messages based on the time of day.

### Changed
- **UI Refinement**: Wrapped main layout in a scrollable view for better accessibility on smaller screens.
- **Track Loading**: Optimized track and album loading with a centralized, state-aware repository pattern.
- **Server Selection**: Improved UX for server switching and connection validation.
- **CI/CD**: Enhanced build pipeline with pre-commit hooks and automated documentation updates.

### Fixed
- **Android Auto**: Reverted to a stable Tile-based interface to resolve navigation and performance issues.
- **Build Stability**: Fixed various compilation errors and resource conflicts in recent feature branches.

## [6.4.0] - 2026-07-05

### Added
- **MuMa Cloud Sync**: Backup entire app configuration to the MuMa database.
- **Settings API**: Integration with the new MuMa User App Settings endpoints.
- **MumaAPIClient**: Modern networking layer for MuMa interactions.
- **Sync UI**: Manual backup and restore buttons in Settings.

## [6.3.3] - 2026-07-05

### Changed
- **LMS API Key**: Replaced dynamic API key fetching with a hardcoded Subsonic API key for LMS servers for simplified setup.

## [6.3.2] - 2026-07-05

### Added
- **API Key Automation**: Automatically fetches Subsonic API keys for LMS servers during setup and connection testing.

## [6.3.0] - 2026-07-05

### Added
- **Welcome Dialog**: New users are now greeted with a setup wizard to enter login credentials.
- **Auto-Server Discovery**: Automatically configures Alpha and Stable LMS servers based on build type.
- **Connection Validation**: Real-time server ping during setup to ensure correct credentials.
- **Dynamic Playlists (Tiles)**: Support for server-side dynamic playlists synced with LMS and Music Management.
- **Debug Features**: Share and view debug logs directly from settings in debug builds.
- **ListenBrainz**: Scrobbling is now enabled by default.

### Changed
- **UI Improvements**: Significant visibility improvements to player controls, including a green pause button.
- **Landscape Player**: Optimized player layout for landscape mode with scrollable controls.
- **Tile Loading**: Delayed initial tile loading until server connection is established.
- **Deployment**: Improved APK distribution with robust fallbacks.
- **Default Settings**: 5-star rating system enabled by default.

## [6.2.0] - 2026-07-04

### Added
- **Spotify-style UI**: Integrated dynamic "Songs" (Green) and "Sets" (Blue) branding throughout the app.
- **Merged Views**: "Songs" and "Livesets" tabs merged into a single view with a brand-aware toggle switch.
- **OLED Black Theme**: Implemented a pure black (#000000) background for OLED displays and removed the light theme.
- **Brand Consistency**: Dynamic accent color updates for switches, sliders, chips, and scrollbars across all fragments.
- **Tooling Upgrade**: Modernized build pipeline with Gradle 9.6.0 and updated core dependencies.
- **Improved About Screen**: Detailed information on `muma/lms` integration and technical build details.
- **Update System**: Enhanced auto-update checker with authentication and version tracking.

## [6.0.0-140] - 2026-07-04

### Added
- Integrated full changelog support for debug builds in the distribution pipeline.
- Added direct link to `changelog.md` in the download portal.

## [5.2.1] - 2026-07-04

### Added
- Automated version increment support to `bup` script (patch, minor, major).
- Automatic synchronization of bundled assets during release.

## [5.2.0] - 2026-07-04

### Added
- Major dependency update: all libraries and Gradle updated to latest stable versions.
- Gradle updated to 8.12.1.
- Updated to AGP 8.7.3.
- Updated to Kotlin 2.1.0.
- Added `debug` and `release` build type support to the build pipeline.
- Added automatic Git tagging for `release` builds in `bup`.
- Added release notes extraction and metadata generation for APKs.

### Changed
- **Project Structure**: Migrated `apk-hoster` to a standalone repository.
- **Project Structure**: Moved all utility scripts to the `scripts/` directory.
- **Configuration**: Replaced `local.properties` with `.env` for better environment management.
- **Pipeline**: Refactored `bup` as a lightweight wrapper for `scripts/build-and-publish.sh`.
- **Pipeline**: Default build type changed to `debug`.

### Removed
- Removed Docker orchestration logic and `docker-compose.yml` (now handled in `apk-hoster` repository).

## [5.1.0] - 2026-07-04
### Added
- Created `scripts/deploy-stack.sh`, a generalized Docker stack deployment tool supporting Portainer discovery, SSH transfer, and intelligent fallbacks.
- Support for initial stack creation: the deployment script now automatically creates the stack if it does not exist yet using a local template.
- Persistent Build Directory: Configured the build system to use a shared folder (`/mnt/user/ultrasonic-builds`) for all APKs and distribution files.
- Generic Docker Image: The `apk-hoster` Docker image is now generic and uses volume mounts for content, avoiding the need to rebuild the image for every new build.
- Auto-update system: Implemented `UpdateChecker` polling `apk-hoster` API on startup.
- Integrated Changelog: Bundled `CHANGELOG.md` and `RELEASE_NOTES.md` into assets; added `Util.showChangelog` for in-app viewing.
- Version Tracking: Added `last_seen_version` to `Settings` for automated update detection and release notes popup.
- Modular build system: `build.sh`, `publish.sh`, and `deploy.sh`.
- Versioned Docker tagging: the `apk-hoster` image is now tagged with both `:latest` and the version name from Gradle (e.g., `:5.1.0`).
- Portainer Webhook support for automated Stack updates.
- Automatic Docker group permission handling via `sg docker` re-execution.
- Integrated `apk-hoster` deployment into the main pipeline.
- `bup` shortcut for full build-publish-deploy workflow.
- Registry authentication pre-checks for Docker Hub.

### Changed
- **Deployment**: Refactored `deploy.sh` to use the new generalized `deploy-stack.sh` helper, simplifying per-project deployment scripts.
- **Deployment**: Enhanced stack discovery to support `PORTAINER_HOST` for pulling master templates.
- **Deployment**: Improved robustness with `base64` template transfer and automated tab-to-space conversion in compose files.
- Migrated all build and deployment configurations to `local.properties`.
- Updated `install.sh` for automated SDK and dependency management.
- Standardized deployment variable names for cross-project compatibility.

### Fixed
- Fixed deployment failure when no existing stack configuration is found on the remote host by providing a local `docker-compose.yml` fallback.
- Fixed empty webpage in `apk-hoster` by bundling the `dist` directory into the Docker image.
- Fixed APK files downloading as ZIP by registering correct MIME types in `apk-hoster`.
- Fixed .env loading logic to skip invalid bash identifiers.
- Fixed non-interactive session hangs in `publish.sh`.

## [5.0.1] - 2026-07-02
### Added
- 'Check for Updates' button in the About screen.
### Fixed
- Patch for initial testing of updated deployment scripts.
