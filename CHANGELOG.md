# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

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
- `bup` shortcut for the full build-publish-deploy pipeline.
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
