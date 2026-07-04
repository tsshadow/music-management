# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

## [3.77.0] - 2026-07-04
### Added
- Modular build system: split `build_and_publish.sh` into `build.sh`, `publish.sh`, and `deploy.sh`.
- Portainer Webhook support for automated deployments.
- Automatic Docker group permission handling using `sg docker` re-execution.
- Standardized `.env` configuration file for deployment settings.
- `bup` shortcut for the full build and publish pipeline.
- Registry authentication pre-check in `publish.sh`.

### Changed
- Updated `install.sh` to handle `.env` creation and dependency checks automatically.
- Unified deployment environment variables (`REMOTE_STACK_PATH`, `DEPLOY_TARGET_NAME`) for multi-repo consistency.

### Fixed
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
