## 🔌 API Specification

The `music-manager` service provides a REST API (FastAPI) for managing the music library, users, and events.

### 🔐 Authentication
- **POST `/users/auth/login`**: Authenticate with username/password and receive an API key.
- **GET `/users/auth/verify`**: Verify the validity of an `X-API-Key`.

### 👤 User & Settings Management
- **GET `/users/`**: List all registered users (Admin only).
- **GET `/users/{user_id}/settings/{app_id}`**: Retrieve application-specific settings (e.g., `app_id=ultrasonic` for MuMa Mobile's settings backup, `app_id=frontend` for the web player's favorite genres).
- **POST `/users/{user_id}/settings/{app_id}`**: Backup application-specific settings.
- **GET `/users/{user_id}/lb-account`**: Get ListenBrainz integration details.

### 🔔 Events
- **GET `/api/events`**: Query the event log. All query parameters are optional and combine as AND filters:
  - `level` (repeatable): restrict to one or more of `INFO`, `WARNING`, `ERROR`, `CRITICAL`. Omitted means all levels; an unknown value returns 400.
  - `source` (repeatable): restrict to one or more of `music-manager`, `downloader`, `importer` — the three processes that call `setup_logging`. The tagger and scanner loops run inside the music-manager process, so their events carry `source=music-manager`. Omitted means all sources; an unknown value returns 400.
  - `since` / `until`: an ISO-8601 timestamp, or a relative form such as `-30m`, `-1h`, `-7d` (minutes/hours/days ago).
  - `q`: substring match against `title` and `message`.
  - `limit`: default 100, capped at 1000.
  - `offset`: default 0.
  - Response: `{"events": [...], "total": <int>, "counts": {"INFO": <int>, "WARNING": <int>, "ERROR": <int>, "CRITICAL": <int>}}`. `total` reflects every filter in the request, including `level`. `counts` is computed with the `level` filter deliberately dropped (every other filter still applies) — it reports how many events each level chip would reveal if selected, not how many the current level selection already shows.
- **DELETE `/api/events/{id}`**: Remove a specific event.
- **DELETE `/api/events`**: Clear all events.

### 📈 Scrobbling & Ratings
- **POST `/api/event`**: General scrobble/playback event endpoint.
- **POST `/api/lms-event`**: Specific endpoint for Logitech Media Server webhooks (syncs ratings).

### 🛠 Management & Rules
- **GET `/api/rules`**: List all active tagging and genre rules.
- **POST `/api/users/sync/lms-db`**: Manually trigger a synchronization with `lms.db`.
- **GET `/api/system/containers`**: Monitor the status of system Docker containers.

### ❤️ Health
- **GET `/health`**: Reports actual service health instead of a hard-coded `ok`. Response: `{"status": "ok"|"degraded", "service": "music-manager", "version": <string>, "database": "ok"|"unreachable", "threads": {"tagger": <bool>, "scanner": <bool>, "radio": <bool>, "events-retention": <bool>, "events": <bool>}}`. `threads` covers the long-running background loops plus the event worker; one-shot startup tasks are deliberately excluded, since registering them would pin the endpoint to `degraded` within a minute of every restart. `status` is `degraded` — and the HTTP status code is 503 — when the database is unreachable or any of those threads has died.
