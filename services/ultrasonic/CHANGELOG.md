# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **An "Interface size" setting under Appearance, defaulting to 75%.** The layouts hardcode their
  dp values instead of using dimension resources, so there was no single place to make the UI
  denser. `UiScaleHelper` now wraps the activity's base context with a scaled `densityDpi` — the
  same mechanism as the system's "Display size" — which shrinks every dp and sp at once. At 75% the
  album rows land at ~64dp with 48dp artwork and 13.5sp titles, instead of ~86dp with 64dp artwork
  and 18sp titles, which is roughly Spotify's list geometry. Selectable between 100% and 70%;
  changing it recreates the activity through the existing theme-changed event. Note that at 75% a
  48dp touch target renders as 36dp, below the accessibility minimum, which is why the setting can
  be turned back up.

- **Favorite genres, shared with the web player.** Long-pressing a genre in Library → Genres opens a
  context menu that adds or removes it; favorites are drawn with a star and sorted above the
  recently-picked ones. The list lives in the same place the web UI keeps it — the MuMa per-app
  settings blob under `app_id = "frontend"`, key `favoriteGenres` — so both clients see one list.
  `FavoriteGenres` (in `home/`) reads and writes it through the existing generic
  `getMumaSettings`/`saveMumaSettings` calls, merging into the blob so keys the web UI owns survive,
  and keeps a local copy in `Settings.favoriteGenres` so the list works offline and on Android
  Auto's thread. A push that fails is logged and retried by the next toggle; the local edit is never
  lost.
- **A Favorites folder in Android Auto**, with a Genres and a Playlists subfolder. A favorite genre
  plays straight from the folder — no year or sort-method level in between — and the playlists
  subfolder holds the dynamic playlists whose star is set in the filter modal, which is the first
  thing `TileInfo.favorite` is actually read for. Root and subfolders only appear when they have
  content, and both sources are local, so the root request still makes no network call.

### Changed
- **Default song/liveset tiles are now era-specific instead of plain genre tiles**: the eight
  single-genre defaults (Euphoric Hardstyle, Hardstyle, Mainstream Hardstyle, Raw Hardstyle,
  Hardcore, Mainstream Hardcore, Uptempo Hardcore, Bouncy Uptempo) duplicated the genre list,
  which reaches the same result on its own. Replaced by three genre + year-window tiles the genre
  list cannot express: Hardstyle Classics (Mainstream Hardstyle, 2009-2017), Millennium Hardcore
  (Mainstream Hardcore, 2010-2015) and Early Uptempo (Uptempo Hardcore, 2012-2017), all randomly
  sorted. Year lists are enumerated per year because the server resolves `YEAR` filter values to
  exact clusters and has no range support. Applies to fresh installs without server-side tiles;
  existing installs keep their stored tiles.

## [6.5.20] - 2026-07-31

### Added
- **A "Log out" entry in the toolbar overflow menu.** Signing out previously meant clearing the app
  data or reinstalling. It confirms first, stops playback, clears `Settings.staticPassword`, the
  MuMa API key/user id and the encrypted MuMa tokens, resets the music service, and reopens the
  welcome/login dialog with the username prefilled. Downloads are untouched.
- **Skeleton placeholders on the home screen.** `HomeSectionState` gives every section its own
  Loading/Empty/Content state, so each slot shows pulsing placeholders
  (`home_skeleton_carousel`/`home_skeleton_grid`, `@anim/skeleton_pulse`) until its own data
  arrives instead of the whole screen staying black until the slowest section finished. A reload
  keeps sections that are already on screen.

### Changed
- **The home screen loads concurrently.** `HomeViewModel.load()` launches one coroutine per
  provider and publishes each section as it completes, and `LibraryActivityProvider` fetches its
  artists, albums and labels/festivals with `async` instead of one after another — six sequential
  round trips became two rounds of three parallel ones.

### Fixed
- **A password rejected mid-session returns to the login screen.** Subsonic error 40 was only ever
  turned into a message by whichever screen happened to make the call, so a password changed on the
  server left the app permanently broken with no way back to the login screen.
  `AuthenticationFailureNotifier` (in `core/subsonic-api`, called from both `throwOnFailure()`
  overloads) now reports it, `UApp` republishes it on `RxBus`, and `NavigationActivity` ends the
  session and shows the login screen with an explanation. Only error 40 does this: errors 50 (not
  authorized) and 70 (not found) leave the session alone.

## [6.5.19] - 2026-07-31

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

## [6.5.18] - 2026-07-31

### Added
- **Beheer-tab**: onderin is er een vierde tab bijgekomen die de beheerpagina's van de webui
  spiegelt. Voor nu: Downloaders (SoundCloud-accounts en YouTube-kanalen), Gebruikers (bekijken,
  in- en uitschakelen) en Verzoeken (goedkeuren, terugdraaien, afwijzen). De tab is alleen zichtbaar
  als je beheerder bent.

### Added
- **Vier tabbladen erbij in Library**: Jaren, Festivals, Lineups en Ratings, naast Playlists,
  Genres, Artiesten, Albums en Opgeslagen. Zoeken op lineup kan daarmee weer.

### Changed
- **In sets-modus tonen de carrousels op de startpagina festivals in plaats van labels.** Livesets
  zijn festivalopnames, dus een platenlabel zegt er weinig over.

## [6.5.17] - 2026-07-31

### Fixed
- **Een artiest aantikken op de startpagina leverde niets op.** De carrousels bevatten ook remixers
  en gastartiesten zonder eigen albums, waardoor je op een leeg scherm belandde. Er staan nu alleen
  nog artiesten met eigen releases in.
- **Een label aantikken leverde niets op.** De labels kwamen uit een andere tabel dan waarop
  gefilterd wordt, dus zoeken op zo'n naam gaf nul resultaten. Beide gebruiken nu dezelfde bron.
- **Artiestafbeeldingen op de startpagina** worden weer onder de juiste sleutel en op groot formaat
  opgehaald, zodat ze gedeeld worden met de rest van de app in plaats van elke keer opnieuw geladen.

## [6.5.16] - 2026-07-31

### Added
- **Library tab**: one place for everything you browse by type — dynamic playlists, genres,
  artists, saved playlists and albums — as swipeable pages under a tab strip.

### Fixed
- **Browsing was unreachable in 6.5.15**: removing the home screen's filter chips also removed the
  only way into dynamic playlists, genres, the album list and the artist list. Creating a dynamic
  playlist was impossible, since that happens on the same screen. The Library tab brings all of it
  back.
- **The Favorieten tab showed a copy of the home screen.** It now shows starred albums, starred
  artists and everything you rated four stars or better; tapping a track plays it.

### Changed
- **Bottom navigation is now Home, Library and Favorieten.** Zoeken left the bottom bar because the
  toolbar already has a search field, and playlists moved into Library.

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
