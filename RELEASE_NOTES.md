# Release Notes - LMS 3.82.4

## Version 3.82.4 (2026-07-05)
### 🔗 MuMa Integration & UI Enhancements
- **MuMa Resource API**: Integrated a new `/muma` API endpoint for seamless communication with the MuMa Control Center. This enables centralized authentication and cross-app settings synchronization.
- **Smart Playlist Migration**: Migrated all dynamic playlist logic to the MuMa core. LMS now acts as a dedicated playback engine while offloading complex playlist rules to the management layer.
- **MX Master 3 Support**: Enhanced the web interface with horizontal scroll wheel support for volume control, optimized for the Logitech MX Master 3 thumbwheel.
- **Volume Bar Scrolling**: Added vertical scroll wheel support directly on the volume slider for more intuitive audio management.
- **Subsonic API Cleanup**: Removed legacy SmartPlaylist endpoints in favor of the new MuMa-driven dynamic playlists.

## Version 3.79.0 (2026-07-04)

LMS 3.77.0 focuses on rebranding the project to MuMa Server, improving Subsonic API compatibility, enhancing the web interface MuMa Spotify, and refining the deployment pipeline.

### Branding & UI
- **MuMa Server**: Renamed "Lightweight Music Server" to "Lightweight MuMa Server (LMS)".
- **MuMa Spotify**: The web interface has been rebranded to MuMa Spotify, featuring Spotify-inspired styling.
- **Update Notifications**: You will now be automatically notified of new updates with a dedicated release notes modal.
- **Persistent Release Notes**: A full history of changes is now accessible anytime via the "About" section in the MuMa Spotify interface.

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
