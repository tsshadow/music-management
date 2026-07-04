# Release Notes - LMS 3.77.0

## Version 3.77.0 (2026-07-04)

LMS 3.77.0 focuses on improving Subsonic API compatibility, enhancing the web interface, and refining the overall music management experience.

### Features
- **Spotify UI Update Notifications**: You will now be automatically notified of new updates with a dedicated release notes modal.
- **Persistent Release Notes**: A full history of changes is now accessible anytime via the "About" section in the Spotify-inspired web interface.
- **Subsonic API Enhancements**: Added support for `coverArt` in `discTitle` responses and enabled searching for albums and artists using MusicBrainz Identifiers (MBID).
- **Artist Role Filtering**: New optional role filter for the "appears on" section in artist views, allowing for cleaner browsing of guest appearances.
- **Podcast Support**: Initial support for podcasts via the Subsonic API has been implemented.
- **UI Codec Filtering**: The web interface now supports filtering tracks and albums by audio codec (e.g., FLAC, MP3).

### Improvements
- **Scanning Performance**: Optimized library scanning by processing audio properties, metadata, and embedded images in a single pass, significantly reducing scan times for large libraries.
- **Accessibility**: Improved support for screen reader users across the primary navigation and playback controls.
- **Audio Reliability**: Enhanced audio property decoding and fixed playback initialization issues on some mobile browsers.
- **Queue Management**: Added labels to tracks in the playback queue for better context during long sessions.
