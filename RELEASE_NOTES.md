# Release Notes - LMS 3.77.0

## Version 3.77.0 (2026-07-04)

LMS 3.77.0 focuses on improving Subsonic API compatibility and refining the user interface for a better music management experience.

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
