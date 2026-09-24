## 🔌 API Specification

The `music-manager` service provides a REST API (FastAPI) for managing the music library, users, and events.

### 🔐 Authentication
- **POST `/api/auth/login`**: Authenticate with username/password and receive an API key. The
  session endpoints (`/api/auth/*`) and `GET /api/roles` are the only `users` routes under the bare
  `/api` prefix; every other user route is under `/api/users` only (there is no `/api/{user_id}/...`,
  and no `/api/users/auth/*`).
- **GET `/api/auth/verify`**: Verify the validity of an `X-API-Key`.

Every route below takes the key in `X-API-Key` and resolves it through the one
`routers.users.verify_api_key` (401 without a key, 403 for an unknown or disabled one). "Admin"
means the admin role (`rbac.require_admin`); a named permission means `rbac.require_permission`.
The system key passes every check. Routes not marked otherwise need any authenticated account.

### 👤 User & Settings Management
- **GET `/users/`**: List all registered users (`users.read`). The rows do **not** carry `api_key`
  (removed in the RBAC-gaps fix: the api_key is password-equivalent).
- **POST|PUT `/users/{user_id}/password`**: Body `{"password": ..., "current_password": ...}`. Another
  account's password, and any admin's, needs the admin role. A non-admin changing their own must send
  `current_password` (403 when missing or wrong); an account without a password yet may set its first.
- **POST `/users/sync/lms-db`** (also `/sync/lms`, `/sync/muma-server`): run the lms.db sync now and
  return `{"synced": <int>}`. Admin only; 409 while a sync (manual or the hourly loop) is running.
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
  - Any authenticated account may list events (the Home Assistant REST sensor uses this).
- **DELETE `/api/events/{id}`**: Remove a specific event. Admin only.
- **DELETE `/api/events`**: Clear all events. Admin only.

### 📈 Scrobbling & Ratings
- **POST `/api/event`**: General scrobble/playback event endpoint.
  - `artist_name`, `track_title`, `username`: required.
  - `source`: where the play happened — `frontend`, `mobile`, `auto` (phone in the car), `lms-web`,
    `listenbrainz`. Defaults to `manual`. Listens recorded before 2026-08 carry the historical
    constant `lms`, which meant "played through the server" and said nothing about the device.
  - `played_secs`: seconds actually played. Optional; `NULL` when the client did not report it, which
    is not the same as zero and must not be read as such. A non-positive value is stored as `NULL`.
  - Both new fields are optional in both directions: a client that sends neither behaves exactly as
    before. See [docs/designs/wrapped/technical.md](designs/wrapped/technical.md).
- **POST `/api/rating/lms-event`** (alias `/api/rating/server-event`): the LMS rating webhook. System key
  only (403 for any user key, admin included): the body names the `username` the rating is stored under.
- **GET `/api/rating/ratings/{username}`**: an account's ratings. Own username, or admin/system key.

### 🛠 Management & Rules
- **GET `/api/rules`**, `/api/artists`, `/api/labels`, `/api/label-proposals`, `/api/config`, `/api/about`,
  `/api/stats`, the curation queues and the downloader account lists: any authenticated account.
- **`rules.manage`**: `POST /api/rules/genres/{id}/decide`, `POST /api/rules/podcasts/{id}/decide|rename`,
  `POST|DELETE /api/rules/podcasts/{id}/aliases`, `POST /api/rules/artist-genres`,
  `DELETE /api/rules/artist-genres/{id}`, `POST /api/rules/label-genres`, `DELETE /api/rules/label-genres/{id}`,
  `POST /api/rules/artist-redirects`, `DELETE /api/rules/artist-redirects/{id}`,
  `POST /api/label-proposals/{id}/confirm|reject`, `POST /api/tagger/rescan`, `POST /api/tagger/rescan/file`.
- **Admin**: `POST /api/soundcloud`, `DELETE /api/soundcloud/{name}`, `POST /api/youtube`,
  `DELETE /api/youtube/{name}`.
- **GET `/api/system/containers`**: the installation's Docker containers. Admin only.
- **GET `/api/system/logs/{name}?tail=`**: one container's log tail. Admin only; `name` must be a container
  the list above returns (exact name, not an id), otherwise 404.

### 🎨 Artist images
- Reads (`/api/artists/search`, `/search-all`, `/images/stats`, `/fetch-progress`, `/manage/search`,
  `/{id}/images`) need any authenticated account; `GET /api/artists/{name}/image` is public.
- **`rules.manage`**: `POST /api/artists/{id}/image/url`, `/image/upload`, `/image/select/{image_id}`,
  `/image/clear`, `POST /api/artists/fetch-missing` (alias `/fetch-images`), `POST /api/artists/{id}/fetch-image`.
- `/image/url` accepts only http(s) URLs whose host resolves to public addresses (400 otherwise; each
  redirect hop is re-checked) and downloads at most 10 MB (413). `/image/upload` takes base64 of at most
  10 MB (413).

### ❤️ Health
- **GET `/health`**: Reports actual service health instead of a hard-coded `ok`. Response: `{"status": "ok"|"degraded", "service": "music-manager", "version": <string>, "database": "ok"|"unreachable", "threads": {"tagger": <bool>, "scanner": <bool>, "radio": <bool>, "events-retention": <bool>, "events": <bool>}}`. `threads` covers the long-running background loops plus the event worker; one-shot startup tasks are deliberately excluded, since registering them would pin the endpoint to `degraded` within a minute of every restart. `status` is `degraded` — and the HTTP status code is 503 — when the database is unreachable or any of those threads has died.
