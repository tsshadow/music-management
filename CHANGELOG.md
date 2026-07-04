# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [2.1.26] - 2026-07-04
### Fixed
- **LMS Sync**: Authenticatieprobleem met de LMS Subsonic API opgelost door de `apiKey` parameter expliciet toe te voegen aan de sync-URL.

## [2.1.25] - 2026-07-04
### Fixed
- **API Security**: Inconsistenties in API-sleutels tussen microservices en het Control Center opgelost in Docker Compose configuraties.
- **LMS Sync**: Bevestigd dat de `user-service` de juiste `X-API-Key` meestuurt naar LMS tijdens de gebruikerssynchronisatie.

## [2.1.24] - 2026-07-04
### Added
- **YouTube Management**: YouTube-accounts kunnen nu worden beheerd via het Control Center.
- **Cookie Support**: Ondersteuning toegevoegd voor Firefox-cookies uit een gedeeld Docker-volume voor zowel YouTube als SoundCloud downloaders.

### Fixed
- **UI Consistency**: SoundCloud en YouTube beheerpagina's zijn nu consistent en ondersteunen verwijderen van accounts.

## [2.1.23] - 2026-07-04
### Fixed
- **User Service**: Fixed syntax and logic errors in LMS synchronization (`run_lms_sync`).
- **Configuration**: Added `LMS_HOSTS` support for multiple LMS instances and fixed `LMS_HOST` typo in `.env`.

## [2.1.22] - 2026-07-04
### Added
- **API Security**: Systeem-brede API-key validatie (`X-API-Key`) geïmplementeerd voor alle microservices.
- **Control Center**: Mogelijkheid toegevoegd om de API-sleutel in te stellen en op te slaan in het dashboard.
- **User Service**: `user-service` toegevoegd aan de `full` docker-compose configuratie.

### Fixed
- **API Consistency**: De `API_KEY` is nu gesynchroniseerd over alle services (`management-api`, `user-service`, `scrobble-service`, `rating-system`).
- **LMS Configuration**: De standaard LMS host gecorrigeerd naar `lms.teunschriks.nl`.

## [2.1.20] - 2026-07-04
### Fixed
- **LMS Configuration**: De standaard LMS host gecorrigeerd naar `lms.teunschriks.nl` en CORS origins bijgewerkt naar de juiste productie-IP (192.168.1.27).

## [2.1.19] - 2026-07-04
### Added
- **User Password Management**: Wachtwoorden instellen via Control Center met automatische synchronisatie naar LMS.
- **Security**: Bcrypt hashing geïmplementeerd voor veilige opslag van gebruikerswachtwoorden.

## [2.1.18] - 2026-07-04
### Added
- **User Migration**: Geïmporteerd van gebruikers uit `lms.db` naar de User Service.
- **LMS Integration**: Ondersteuning toegevoegd voor directe SQLite database synchronisatie vanuit LMS.
- **UI Enhancements**: Nieuwe synchronisatie-opties toegevoegd aan het Users dashboard.

## [2.1.17] - 2026-07-04
### Added
- **User Service**: Nieuwe microservice voor centraal gebruikersbeheer en externe account koppelingen (ListenBrainz).
- **Control Center**: Nieuw "Users" dashboard voor het beheren van gebruikers en hun API keys.
- **LMS Sync**: Mogelijkheid om gebruikers/spelers direct vanuit Logitech Media Server te synchroniseren.
- **Scrobble Integration**: Geïntegreerde ListenBrainz imports gebaseerd op opgeslagen gebruikersprofielen.

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
- **Design System**: Created `styleguide.md` to formalize the Spotify-inspired dark theme (Groen/Zwart/Grijs).
- **UI Refinement**: Standardized all UI accent colors to Spotify Green (`#1DB954`) and improved focus/selection states.

## [2.1.11] - 2026-07-04
### Added
- **Centralized Release Notes**: The Control Center now aggregates and displays release notes and changelogs from all modular services.
- **Service API Expansion**: Added versioning and release notes endpoints to the Rating System service.

## [2.1.10] - 2026-07-04
### Added
- **Modular Containerization**: Split the monolithic application into 10 specialized, lightweight services (`muma-scanner`, `muma-tagger`, `muma-downloader`, etc.).
- **Smart Build System**: Introduced `scripts/affected.sh` and optimized `bup` to skip builds for unedited modules.
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
- **Streamlined Workflow**: Updated `bup` to use the new centralized deployment script.

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
