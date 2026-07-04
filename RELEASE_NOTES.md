# Release Notes - LMS 3.78.1

## Version 3.78.1 (2026-07-04)

LMS 3.77.0 focuses on rebranding the project to MuMa Server, improving Subsonic API compatibility, enhancing the web interface MuMaFi, and refining the deployment pipeline.

### Branding & UI
- **MuMa Server**: Renamed "Lightweight Music Server" to "Lightweight MuMa Server (LMS)".
- **MuMaFi**: The web interface has been rebranded to MuMaFi, featuring Spotify-inspired styling.
- **Update Notifications**: You will now be automatically notified of new updates with a dedicated release notes modal.
- **Persistent Release Notes**: A full history of changes is now accessible anytime via the "About" section in the MuMaFi interface.

### Deployment & Build System
- **Enhanced Pipeline**: Split `build_and_publish.sh` into focused `build.sh`, `publish.sh`, and `deploy.sh` scripts.
- **Debug & Release Modes**: New support for `debug` (alpha/latest) and `release` (stable) builds with intelligent Docker tagging.
- **Docker Conflict Resolution**: Removed hardcoded container names to allow multiple parallel deployments without conflicts.
- **bup Utility**: Added a `bup` shortcut for one-command build, publish, and optional deployment.

### Features
- **Subsonic API Enhancements**: Added support for `coverArt` in `discTitle` responses and enabled searching for albums and artists using MusicBrainz Identifiers (MBID).
- **Artist Role Filtering**: New optional role filter for the "appears on" section in artist views, allowing for cleaner browsing of guest appearances.
- **Podcast Support**: Initial support for podcasts via the Subsonic API has been implemented.
- **UI Codec Filtering**: The web interface now supports filtering tracks and albums by audio codec (e.g., FLAC, MP3).

### Improvements
- **Scanning Performance**: Optimized library scanning by processing audio properties, metadata, and embedded images in a single pass, significantly reducing scan times for large libraries.
- **Accessibility**: Improved support for screen reader users across the primary navigation and playback controls.
- **Audio Reliability**: Enhanced audio property decoding and fixed playback initialization issues on some mobile browsers.
- **Queue Management**: Added labels to tracks in the playback queue for better context during long sessions.
