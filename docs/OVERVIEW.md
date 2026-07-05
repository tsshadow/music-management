### MuMa Ecosystem System Overview

This file provides a concise summary of the main blocks within the MuMa ecosystem. For details, see `README.md`.

---

#### 1. Management Layer (MuMa Control)
*   **Core**: Central management platform (`music-management`) running in Docker.
*   **Services**: `user-service` (auth), `scrobble-service` (stats), `rating-system`.
*   **Workers**: Automate downloading (YT/SC/TG), tagging, scanning, and ML analysis.
*   **Access**: Dashboard at `muma.teunschriks.nl`.

#### 2. Playback Layer (LMS & UI)
*   **Engine**: Logitech Media Server (LMS) as backend for audio streaming.
*   **Frontends**: Custom Spotify-style interface in Svelte.
*   **Instances**: `Stable` for daily use, `Alpha` for UI tests.
*   **Feature**: Playback data in LMS is volatile; metadata is stored in MuMa.

#### 3. Client & Distribution Layer
*   **Mobile**: Ultrasonic Android app, connected via Subsonic API.
*   **APK Hoster**: Own service for hosting and updating the Ultrasonic APK.
*   **Integration**: Direct link from the Spotify-style UI to MuMa Control (for admins).

#### 4. Database Architecture
*   **MuMa MariaDB**: Persistent "Source of Truth". Contains `library` (metadata), `listens` (history), `rules` (tagging), and `downloads` (queues).
*   **LMS SQLite**: Volatile database for playback state and API access.
*   **APK Hoster DB**: Manages versions and access for mobile app distribution.

#### 5. Dataflow & Connectivity
*   **Authentication**: Users validate against `lms.db` via the `user-service`.
*   **Ingestion**: Pipeline of download -> tagging -> MariaDB -> LMS rescan.
*   **Sync**: Ratings and scrobbles are sent from all clients to the central MuMa services.
*   **Network**: All communication occurs via reverse proxies at `*.teunschriks.nl`.
