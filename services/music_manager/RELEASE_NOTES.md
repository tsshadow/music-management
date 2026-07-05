# Music Manager Release Notes

## Version 1.3.0 (2026-07-05)
### ☁️ Cloud Sync & Enhanced Core
- **Settings Backup API**: Introduced `/api/users/{user_id}/settings/{app_id}` for cross-device configuration sync (initially for Ultrasonic).
- **Unified Authentication**: The `api_key` returned during login is now fully authorized for all API interactions, including stats and settings.
- **Improved Scrobbling**: Added high-capacity pagination to ListenBrainz imports, allowing historical sync of thousands of tracks.
- **Better Stats**: Revamped library analytics with accurate ML-based genre matching and duration tracking.
- **Security Hardening**: Removed explicit API key management from the UI to promote safer, session-based authentication.

## Version 1.0.0 (2026-07-05)
### 🚀 The Great Consolidation
- **Six services in one**: The following services have been consolidated into the unified Music Manager:
  - Management API (Control Center)
  - User Service (Authentication & LMS Sync)
  - Scrobble Service (ListenBrainz integration)
  - Rating System (Track popularity)
  - Stats Service (Library analytics)
  - Artist Image Fetcher (Artwork management)
- **Performance**: Reduced resource overhead by running a single FastAPI instance with optimized database connection pooling.
- **Stability**: Fixed "Aborted connection" issues by implementing persistent pooling.
- **Unified UI**: The Control Center dashboard is now served directly by the Music Manager.
- **Multi-LMS Support**: Automatically discovers and enriches both Stable and Alpha LMS instances.
