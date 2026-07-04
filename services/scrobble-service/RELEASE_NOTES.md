# Release Notes - Scrobble Service

## Version 2.1.14 (2026-07-04)
### 🚀 Initial Release
- **Scrobble Tracking**: Added support for receiving and storing scrobble events.
- **Smart Matching**: Implemented track matching logic with fallback to artist/title if MBID is missing.
- **ListenBrainz Integration**: Added functionality to import listening history from ListenBrainz.
- **Dual Table Storage**: Separate storage for confirmed (`scrobble_listens`) and unmatched (`scrobble_unmatched_listens`) scrobbles.
