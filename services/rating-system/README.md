# Muma Rating System

A centralized rating system for tracks, artists, genres, and more.
It integrates with LMS (Lightweight Music Server) and provides cross-instance synchronization.

## Architecture

- **Backend**: Python FastAPI
- **Database**: MariaDB (shared with `music-management`)
- **Identification**: Uses `track_uid` (from `music-management`) for tracks, and names for artists/genres.

## API Endpoints

- `POST /ratings`: Set a rating.
- `GET /ratings/{entity_type}/{entity_id}`: Get ratings for an entity.
- `GET /ratings/user/{username}`: Get all ratings for a user.
- `GET /ratings/updates?since={iso_timestamp}`: Fetch updates since a specific time (used for sync).
- `POST /api/lms-event`: Compatibility endpoint for LMS `MusicManagementBackend`.

## LMS Integration

To enable this in LMS, set the following in `lms.conf` or environment:
`music-management-api-url=http://rating-system:8000/api/lms-event`

Ensure the `MusicManagement` feedback backend is enabled in your user settings.

## Synchronization

Multiple LMS instances can stay in sync by:
1. Pushing ratings to this service (automatic via `MusicManagementBackend`).
2. Periodically pulling updates via `/ratings/updates`.

A dedicated sync worker can be added to the `music-management` stack to push ratings back to LMS instances if they support an import API.
