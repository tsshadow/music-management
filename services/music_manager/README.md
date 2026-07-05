# Music Manager v1.3

The **Music Manager** is a centralized management platform and API core for the MuMa music ecosystem. It consolidates multiple microservices into a single, efficient application to provide a unified interface for music library administration, user authentication, listening history, and metadata enrichment.

### Core Features

- **Consolidated API**: A single FastAPI-based backend (port 8000) that handles:
  - **User Management**: Authentication, admin permissions, and external service tokens (ListenBrainz).
  - **Scrobbling**: Tracking listening history and matching tracks to the library.
  - **Ratings**: Synchronizing song ratings between Spotify UI, LMS, and Ultrasonic.
  - **Stats**: Providing library insights and listening trends.
  - **Artist Enrichment**: Automated fetching and syncing of high-quality artist images.
- **Control Center Dashboard**: A modern Svelte-based frontend (port 8003) for:
  - Monitoring system health and container status.
  - Managing dynamic/ML-based playlists.
  - Viewing real-time system logs and activity.
  - Configuring external integrations (YouTube, SoundCloud, Telegram).
- **LMS Integration**: Deep synchronization with Logitech Media Server instances (Stable & Alpha).
- **Infrastructure**: Optimized with database connection pooling and thread-safe processing.

### Architecture

The Music Manager acts as the brain of the MuMa ecosystem, orchestrating specialized workers (Scanner, Tagger, Downloader, ML Analyzer) and providing the data backbone for playback clients.

### Versioning

This application follows its own versioning cycle, independent of the individual worker modules.

- **Current Version**: v1.3.0
- **Release Date**: 2026-07-05
