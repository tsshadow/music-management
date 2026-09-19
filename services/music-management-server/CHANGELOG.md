# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Every track is filed under a `QUALITY` cluster, and `getSpotifyTracks` takes a floor on it.**
  `lossless` / `320` / `aac` / `192` / `low`, the five tiers muma's `format_tier()` ranks the
  versions of a song by, derived from the codec and the bitrate the scanner already reads.
  Lossless is a codec decision (an ALAC `.m4a` is lossless, PCM counts although the codec table
  does not flag it) and the AAC family sits above a 192 mp3 at the same bitrate. Migration V118
  backfills the existing library from the bitrate and path on the track row -- no rescan, as with
  V116 and V117 -- and leaves the cluster counts at zero for `hasOutdatedStats()` to recompute on
  the next scan. `minQuality=320` on `getSpotifyTracks` means 320 and lossless; an unknown tier is
  an error rather than a filter that falls open, and a library without the cluster type answers
  with nothing rather than everything. `getSongs` needs no change: `QUALITY` is a cluster like
  any other in its `clusters` JSON.
- **`startScan` accepts a `path` parameter and scans only that subtree.** MuMa moves and retags
  files continuously and had no way to say so: the library-wide incremental scan takes the better
  part of an hour here, and it starts an hour after the previous one finished, so a change waited
  up to two hours to become visible -- with the file's old path still in the index in the meantime.
  `path` is repeatable and library-relative (MuMa mounts the tree at `/mnt/music` and this server at
  `/music`, so an absolute path from a client would name a directory that does not exist here); an
  absolute path inside a media library root is accepted too. A path outside every root is refused
  rather than widened to a full scan. **A directory that no longer exists is valid and is the more
  important half:** it is how the rows under a folder that was moved away get removed, so the
  removed-file pass grew a query bounded by a half-open byte range on the path -- not `LIKE`, which
  is case-insensitive for ASCII in SQLite and would also match a sibling directory whose name
  merely starts the same way. Combines with `fullScan` to mean "re-read everything under this path".
  The response echoes `scanStatus.scanScope`, which is the only synchronous way a client can tell
  an accepted scope from an older server that ignored the parameter and started a full scan.
  A scoped scan skips only `Optimize` and the duplicate-file report, and deliberately still runs
  orphan removal and the cluster statistics -- skipping the latter is what once left every genre
  count at zero. It also does not publish its numbers as `lastScan`, so the admin page keeps
  describing the last full scan instead of "3 files".

- **A scoped scan pauses the periodic one instead of aborting it, and it resumes where it was.**
  `requestImmediateScan` aborted the running scan and then recomputed the next scheduled
  moment as "an hour from now"; with an hourly period and a scan that takes the better part of
  an hour, that meant always running, always aborted, and always pushed back, so the
  library-wide scan never got through its own steps -- including the orphan removal and the
  cluster statistics. The pause reuses the flag every scan step already checks on each batch
  boundary; what is new is that the service remembers *why* the flag went up. On resume the
  interrupted step starts again from its own beginning, the steps before it do not, and their
  contribution to the stats survives. Incoming paths are merged into a set and debounced --
  five seconds of quiet, sixty seconds at the outside -- so a tagger round touching hundreds of
  folders costs one step restart per minute rather than hundreds.

- **A weekly full re-read can be scheduled next to the incremental period.** The same
  library-wide scan with `fullScan` on, on a configurable day of the week, off by default
  (`scan_settings.full_scan_period`, database version 117). When both moments coincide the full
  one wins: it does everything the incremental one does. music-manager now sends the folders it
  touched with every move -- both the old and the new path, because the old one is how the rows
  under a folder that is gone get removed -- from its own thread, so a slow music server can
  never hold up an import.

### Fixed
- **A user sync from music-manager now empties the Subsonic auth cache.** A granted password is
  trusted for five minutes (`authGrantedCacheDuration`), so an account disabled on music-manager
  kept being served until its grant lapsed. `IUserSynchronizer` gained an on-sync hook;
  `SubsonicResource` subscribes and clears `AuthCache` on every sync, before the fetch and whether
  or not it succeeds. music-manager pokes the sync on enable/disable, so the refusal now lands on
  the next request.

### Added
- **`getSpotifyTracks` filters on a festival and on a festival lineup.** `festival` resolves
  through the `FESTIVAL` cluster type, exactly like the `genre`, `year` and `podcast` parameters
  beside it, so it needs FESTIVAL in the scanner's extra tags to scan. `lineup` reads the artist
  list out of `/music/metadata/festival-lineups/<name>.txt` -- the same source `getSongs` already
  used for its `festivalLineup` parameter -- and restricts the query to those artists. That match
  is on the whole `artist_display_name`, lowercased, so a lineup naming `Angerfist` does not match
  a track credited to `Angerfist & Outsiders`; two new `Track_findAdvanced` tests pin both the
  cluster filter and that display-name behaviour, which nothing covered before.
- **`getSongs` filters on a set of artists and reports a total.** `artistId` may be repeated; a
  track only survives when it is linked to every artist named, which answers "what did these people
  make together" rather than "any of them". Repeating one id counts once, because the ids enter the
  query as a set -- a self-join would otherwise still mean "this one artist". The `songs` node also
  carries `totalCount`, how many tracks the filter yields rather than how many this page returned,
  so a client can page without walking to the end. `Track::countAdvanced` answers that count, and
  shares its query body with `find_advanced` so the two can never drift apart on a filter.
- **The song node carries the labels.** Read from the PUBLISHER cluster rather than the `db::Label`
  table: labels hang off the release in the data model, and the cluster is what the filtering side
  matches on. Browsing by label already made that same choice.
- **Scrobbling**: A listen now carries how long the track was actually played and where the play
  happened. `MusicManagementBackend::sendScrobble` received the played duration from the player and
  discarded it (`(void)duration;`), and hardcoded `source` to `"lms"`, which made the web player,
  the phone and the car indistinguishable afterwards. `Listen` gained a `source` and a
  `playedDuration`, so both survive the trip from the entry point that knows them to the payload.
  `/rest/scrobble` accepts two optional non-standard parameters, `playedSeconds` and `source`;
  without them the origin is derived from the Subsonic `c=` client name (`spotify` → `frontend`,
  `Ultrasonic` → `mobile`), and the playing time is simply absent. The Wt interface reports
  `lms-web`. A client that knows nothing about any of this scrobbles exactly as before.

### Fixed
- **`setArtist()` and `setArtistName()` looked at two different links in `find_advanced`.** Each got
  its own `track_artist_link` join, so "this id" and "this name" were free to be two different
  artists on two different rows, letting a track through that had one artist as the id and another
  as the name. They now share a single link row, which is the meaning the pair always had.
- **HTTP**: Handlers that proxy to music-management can no longer take the whole
  HTTP thread pool. `handleGetCoverArt` and the five `/muma/*` proxy paths
  blocked on a `std::future` for 10-30s inside `Wt::WResource::handleRequest`;
  with `http-server-thread-count = 0` (one thread per core), enough concurrent
  artist images took the pool between them and the server stopped answering
  anything at all, an unauthenticated ping included, until it was restarted.
  `getCoverArt` -- by far the highest volume, and always answering with an image
  -- now parks on a Wt continuation (`core::http::proxyRequest`) and costs a
  connection instead of a thread. The `/muma/*` paths keep waiting, because they
  forward the upstream status verbatim and Wt commits response headers before a
  continuation resumes, but at most half the pool may wait at once
  (`core::ConcurrencyGate`); past that they answer 503 rather than queue.
- **Subsonic**: `getCoverArt` declares `image/jpeg` up front rather than
  forwarding MuMa's exact subtype, which is no longer knowable by the time the
  headers are written. Browsers sniff the real format; a png or webp still
  renders.
- **HTTP**: `handleGetCoverArt` reuses one client per MuMa base URL instead of
  building and tearing one down per request. `~SendQueue` aborts its in-flight
  request and spins on `std::this_thread::yield()` until that lands, so the old
  code ran a busy-wait on an HTTP thread on the hottest path in the server.
- **HTTP**: A transport error backs off the request that failed instead of the
  whole `SendQueue`. One unreachable artist image used to throttle all outbound
  traffic -- scrobbles and ratings with it -- for 30s, and re-queue itself at
  the head. The queue is only paused once several requests in a row fail, which
  is what actually indicates the endpoint is down.
- **Auth**: `AuthTokenService::processAuthToken` resolves a token under a read
  transaction and only escalates to a write transaction once it is known to
  exist. An unknown key used to take the process-wide exclusive lock for
  nothing on every attempt, queueing behind the scanner's write batches.
- **Auth**: `SubsonicResource` caches authentication failures as well as
  successes (`AuthCache`, 30s, bounded at 1000 entries with grants preferred
  over denials on eviction), so a client stuck on a stale key stops reaching
  the database on every request.
- **Subsonic**: `getCoverArt` forwards MuMa's real status. A missing artist
  image is a 404, but arrived through `onFailureFunc` as a 502, which is why
  the log filled with gateway errors that were never gateway problems.
- **Subsonic**: `getCoverArt` no longer fails for artists whose picture
  music-management does not have. A MuMa-backed cover art id whose proxied
  request 404s (or times out, or has no MuMa configured at all) now falls back
  to the artist's own preferred artwork, or the cover of their earliest
  release, instead of returning the error status that makes clients draw a
  placeholder. Resolved per request rather than in `createArtistNode`, so the
  id keeps pointing at MuMa and the real artist picture wins as soon as it
  exists.

### Changed
- **Database**: Auth tokens moved from the in-memory `volatile` schema into the
  main database (migration to schema version 116). Every LMS restart used to
  discard every provisioned Subsonic API key, which no client can tell apart
  from a wrong key -- they simply retry one that will never work again. The
  legacy `main.auth_token` table left over from before the move is replaced
  outright; nothing has been able to read it since.

### Added
- **UI**: Restored the legacy Wt-based admin/explore UI (library, user and
  scan administration) as a separate entry point on `/legacy`, alongside the
  Svelte-based MuMa Spotify UI.
- **MuMa/Auth**: New `MusicManagementPasswordService` validates Subsonic/MuMa
  logins directly against the music-management user directory; `MumaResource`
  gained a `/muma/users/sync` endpoint.

### Changed
- **Deployment**: Consolidated to a single `lms` container (the separate
  `lms_alpha` compose service was removed) fronted by a new `nginx`
  reverse-proxy service, so `spotify.<domain>` now serves the Svelte frontend
  directly at `/` instead of LMS's bare Wt bootstrap page, while `/rest` and
  `/muma` are still proxied through unchanged. See `docs/deployment.md`.
- **UI**: Moved the embedded Svelte "MuMa Spotify" frontend from
  `src/lms/ui/src` to `src/lms/ui/spotify-ui/src`; it is now served from the
  docroot's `spotify` folder (previously `muma-spotify`).
- **Database**: Strengthened ID type safety across all database objects
  (`AuthToken`, `Listen`, `PlayQueue`, rated/starred artists/releases/tracks,
  `TrackBookmark`, `TrackLyrics`, `UIState`, `User`); owners are now resolved
  by ID instead of a cached object reference.

### Fixed
- **MuMa Integration**: Corrected the feedback/scrobbling API paths sent to
  music-management (`music-management-url` already includes the `/api`
  prefix, so the extra `/api/` segment produced wrong routes).
- **Scrobbling**: `listenStarted` no longer forwards a "now playing" event to
  music-management, since its `/scrobble/event` endpoint can't distinguish
  it from a real listen; only `listenFinished` reports a listen now.
- **Subsonic API**: Fixed the `setSubsonicDefaultTranscodingOutputFormat`
  typo and adapted playlist/bookmark endpoints to the new ID-based
  user/track-list references.

## [3.83.1] - 2026-07-14

## [3.83.0] - 2026-07-11

### Changed
- **UI**: Migrated MuMa Spotify UI from `src/lms/ui/spotify-ui` to `src/lms/ui` and updated build scripts.
- Refactored `muma` module into a standalone static library for better modularity.
- Improved build system integration for MuMa resource handling.

### Removed
- **UI**: Removed legacy Wt-based user interface in favor of the new Svelte-based MuMa Spotify UI.

## [3.82.9] - 2026-07-08

## [3.82.8] - 2026-07-07

## [3.82.7] - 2026-07-07

## [3.82.6] - 2026-07-07

## [3.82.5] - 2026-07-07

## [3.82.4] - 2026-07-07

## [3.82.3] - 2026-07-07

## [3.82.2] - 2026-07-07

## [3.82.1] - 2026-07-07

## [3.82.0] - 2026-07-06

## [3.81.0] - 2026-07-06

## [3.80.0] - 2026-07-05

### Added
- **MuMa Resource**: New dedicated `/muma` API resource for management and synchronization.
- **Settings Sync**: Server-side UI state persistence via MuMa.
- **UI**: Horizontal wheel support for volume control (MX Master 3).
- **UI**: Mouse wheel volume control when hovering the volume bar.

### Changed
- **Architecture**: Migrated SmartPlaylist logic to the external MuMa service.
- **Subsonic API**: Removed SmartPlaylist support from Subsonic endpoints in favor of MuMa dynamic playlists.

## [3.79.0] - 2026-07-05

### Added

## [3.78.12] - 2026-07-05

## [3.78.11] - 2026-07-05

## [3.78.10] - 2026-07-05

## [3.78.9] - 2026-07-05

## [3.78.8] - 2026-07-05

## [3.78.7] - 2026-07-05

## [3.78.6] - 2026-07-05

## [3.78.5] - 2026-07-05

## [3.78.4] - 2026-07-04

## [3.78.3] - 2026-07-04

## [3.78.2] - 2026-07-04

## [3.78.1] - 2026-07-04

## [3.78.0] - 2026-07-04

## [3.77.0] - 2026-07-04
### Added
- **Subsonic API**: Added support for token+salt authentication (legacy Subsonic auth) by using the API key as the secret.
- Modular build system: split `build_and_publish.sh` into `build.sh`, `publish.sh`, and `deploy.sh`.
- Build System: Introduced `debug` (default) and `release` modes in `bup` and deployment scripts, with intelligent tagging (`alpha`, `stable`, `latest`).
- Versioned Docker tagging: images are now tagged with the version from CMake (e.g., `:3.77.0`) plus either `:stable` (if `SERVICE_NAME=lms`) or `:latest` (default).
- Portainer Webhook support for automated deployments.
- Automatic Docker group permission handling using `sg docker` re-execution.
- Standardized `.env` configuration file for deployment settings.
- `bup` shortcut for the full build and publish pipeline.
- Registry authentication pre-check in `publish.sh`.
- **Docker Compose**: Updated `docker-compose.yml` with environment variable support and sensible defaults.
- **Docker Compose**: Removed explicit `container_name` to prevent naming conflicts and support multiple environments.
- **Docker Compose**: Updated `docker-compose.yml` with versioned tags, correct service names (`lms`, `lms_alpha`), and optimized `/mnt/` volume paths.
- **MuMa Spotify**: Added a new release notes modal and version update notification system.
- **MuMa Spotify**: Added a persistent "Release Notes" history in the About section.
- **Branding**: Renamed project to "Lightweight MuMa Server (LMS)" and the web interface to "MuMa Spotify".
- Created `scripts/deploy-stack.sh`, a generalized Docker stack deployment tool supporting Portainer discovery, SSH transfer, and intelligent fallbacks.
- Support for initial stack creation: the deployment script now automatically creates the stack if it does not exist yet using a local template.

### Changed
- Reorganized project structure: moved all utility scripts (`build.sh`, `publish.sh`, `deploy.sh`, `install.sh`, etc.) from root to `scripts/` directory, while maintaining the `bup` shortcut in root.
- Updated `install.sh` to handle `.env` creation and dependency checks automatically.
- Unified deployment environment variables (`REMOTE_STACK_PATH`, `DEPLOY_TARGET_NAME`) for multi-repo consistency.
- **Deployment**: Refactored `deploy.sh` to use the new generalized `deploy-stack.sh` helper, simplifying per-project deployment scripts.
- **Deployment**: Enhanced stack discovery to support `PORTAINER_HOST` for pulling master templates.
- **Deployment**: Improved robustness with `base64` template transfer and automated tab-to-space conversion in compose files.
- **Deployment**: Fixed `.env` parsing to correctly handle trailing comments and whitespace.
- **Branding**: Updated all repository references to `muma/lms` on GitHub and Docker Hub.
- **Internal**: Reverted internal C++ and frontend source naming to "Spotify" for developer readability, while maintaining "MuMa Spotify" branding for user-facing components.

### Fixed
- Fixed "orphan containers" warnings during deployment by adding `--remove-orphans` to the deployment scripts.
- Fixed Docker Hub push denial issues by adding proactive login checks.
- Improved SSH deployment reliability by verifying remote Docker Compose paths.

## [3.76.1] - 2026-07-04
### Changed
- Initial stack support and improved deployment scripts.

## [3.76.0] - 2026-03-14
### Added
- **Subsonic API**: Added `coverArt` in `discTitle` responses.
- **Subsonic API**: Support for searching albums and artists using MusicBrainz Identifier (MBID).
- **Artist Views**: Added an optional role filter for the "appears on" section.
- **Configuration**: Added basic checks to ensure configured directories in `lms.conf` exist.

### Fixed
- **ListenBrainz**: Removed UUID constraint on ListenBrainz token.
- **Subsonic API**: Fixed unwanted termination when receiving bad client parameters.

## [3.75.0] - 2026-03-02
### Changed
- **Build System**: Removed unused filesystem CMake scripts.

## [3.74.0] - 2025-12-24
### Added
- **UI**: Support for filtering by audio codec.
- **UI**: Added labels to track list in playback queue.
- **Accessibility**: Improved accessibility for screen reader users.
- **Configuration**: Added `ui-allow-downloads` option in `lms.conf` to enable/disable downloads.
- **OpenSubsonic API**: Implemented transcoding extension.
- **OpenSubsonic API**: Added support for `indexBasedQueue` extension.

### Fixed
- **Transcoding**: Forced channel count setting to workaround incompatible layout issues for some codecs.
- **UI**: Prevented global filters from being applied on artist and release views.

## [3.73.0] - 2025-12-02
### Changed
- **Database**: Now stores container and codec info in the database for UI filtering and optimization.
- **Performance**: Replaced Boost XML writing with manual implementation to improve serialization performance.
- **FFmpeg**: Improved bitrate fallback and audio property decoding.

## [3.72.1] - 2025-11-16
### Changed
- **Subsonic API**: Bumped server protocol version to 1.16.1.
- **Compatibility**: Added `tempus` to the subsonic client list.

## [3.72.0] - 2025-11-12
### Added
- **Database**: Added `rating` field to the database schema.
- **Artist Info**: Added `artist-info-image-file-names` setting and support for `fanart` files.
- **MIME Types**: Added support for TrueAudio.

### Changed
- **Scanning**: Optimized scanning by processing audio properties, metadata, and embedded images in a single pass.
- **Docker**: Upgraded FFmpeg and Wt (4.12.1) in the official Docker image.

### Fixed
- **Stability**: Fixed audio not starting on some mobile devices and fixed crash when filtering by release type.

## [3.70.0] - 2025-09-13
### Added
- **Podcasts**: Initial support for podcasts (Subsonic API).
