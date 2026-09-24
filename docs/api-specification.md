## 🔌 API Specification

The `music-manager` service provides a REST API (FastAPI) for managing the music library, users, and events.

### 🔐 Authentication
- **POST `/api/auth/login`**: Authenticate with username/password and receive an API key. The
  session endpoints (`/api/auth/*`) and `GET /api/roles` are the only `users` routes under the bare
  `/api` prefix; every other user route is under `/api/users` only (there is no `/api/{user_id}/...`,
  and no `/api/users/auth/*`).
  An unknown username and a wrong password both answer `401 Invalid username or password`, at the
  same bcrypt cost; `403 Account disabled` only follows a correct password.
- **GET `/api/auth/verify`**: Verify the validity of an `X-API-Key`. 401 without a key, 403 for an
  unknown key or a disabled account, 503 (`Retry-After: 5`) when the users table cannot be read.
- **POST `/api/auth/setup`**: create the first account, as admin, while no account exists. `409 Setup
  already completed` once one does (was 400); concurrent calls create exactly one admin.

Every route below takes the key in `X-API-Key` and resolves it through the one
`routers.users.verify_api_key` (401 without a key or for a key no account holds, 403 for a disabled
account, 503 when the database cannot be asked -- no router answers "Invalid API key" for an outage
any more). `GET /api/auth/verify` itself still answers 403 for an unknown key. "Admin"
means the admin role (`rbac.require_admin`); a named permission means `rbac.require_permission`.
The system key passes every check. Routes not marked otherwise need any authenticated account.

### 👤 User & Settings Management
- **GET `/users/`**: List all registered users (`users.read`). The rows do **not** carry `api_key`
  (removed in the RBAC-gaps fix: the api_key is password-equivalent).
- **POST|PUT `/users/{user_id}/password`**: Body `{"password": ..., "current_password": ...}`. Another
  account's password, and any admin's, needs the admin role. A non-admin changing their own must send
  `current_password` (403 when missing or wrong); an account without a password yet may set its first.
- **PUT `/users/{user_id}/role`** (`users.assign-role`), **POST `/users/{user_id}/disable`**
  (`users.disable`), **DELETE `/users/{user_id}`**: `409` when the change would leave no enabled
  admin -- demoting, disabling or deleting the last one. Delete answered 400 before and counted
  disabled admins; demote and disable did not check at all. Disabling or demoting an unknown id is
  now 404.
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
- **POST `/api/scrobble/event`**: General scrobble/playback event endpoint.
  - `artist_name`, `track_title`, `username`: required. A user key may only name its own
    `username` (403 otherwise); admins and the system key (LMS) may name anyone.
  - `source`: where the play happened — `frontend`, `mobile`, `auto` (phone in the car), `lms-web`,
    `listenbrainz`. Defaults to `manual`. Listens recorded before 2026-08 carry the historical
    constant `lms`, which meant "played through the server" and said nothing about the device.
  - `played_secs`: seconds actually played. Optional; `NULL` when the client did not report it, which
    is not the same as zero and must not be read as such. A non-positive value is stored as `NULL`.
  - Both new fields are optional in both directions: a client that sends neither behaves exactly as
    before. See [docs/designs/wrapped/technical.md](designs/wrapped/technical.md).
- **POST `/api/rating/lms-event`** (alias `/api/rating/server-event`): the LMS rating webhook. System key
  only (403 for any user key, admin included): the body names the `username` the rating is stored under.
  Body: `{"event", "object_type", "object_id", "username", "rating", "path"?}` where `object_type` is
  `artist`, `release` or `track`, and `path` (tracks only) is resolved to a `track_uid`.
  - `event: "rating_changed"` upserts `rating_tracks`; response `{"status": "success", "entity_id"}`.
  - `event: "rating_removed"` (sent with `rating: 0`) deletes the mirrored row; response
    `{"status": "removed", "entity_id"}`. A `rating_changed` with `rating <= 0` is treated the same
    way, since no star count below 1 exists. Added with bug report 044: before it, clearing a rating
    on the server sent nothing and the old rating stayed in `rating_tracks` for good. An older
    music-manager answers `rating_removed` with `{"status": "ignored"}`, so the server and
    music-manager must be deployed together.
  - Any other `event` is answered with `{"status": "ignored", "reason": "unsupported event type"}`.
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
- **POST `/api/scanner/relink-orphans`** (admin only, `require_admin`): One-off, idempotent repair for
  track rows a retag left without a file (bug report 042). Every fileless `library_tracks` row whose
  normalised title and duration match exactly one track that has a file -- with the same primary
  artist, or the same set of artists in another order -- has its ratings, listens and ml-analyzer
  rows moved to that track and is deleted. Runs in the background under the scanner lock. Response:
  `{"message": "...", "last": <totals of the previous run or null>}`; `409` while a scan or a relink
  is running, `403` for a non-admin key. The totals (`orphans`, `relinked`, `unmatched`, `failed`,
  `ratings_moved`, `ratings_merged`, `listens_moved`, `listens_dropped`, `tracks_deleted`) are also
  written as an `INFO` event titled "Orphaned tracks relinked".
- **GET `/api/scanner/relink-orphans`** (admin only): `{"running": bool, "last": <totals or null>}` --
  the state of the relink above, kept in memory for the life of the process.

### 🎨 Artist images
- Reads (`/api/artists/search`, `/search-all`, `/images/stats`, `/fetch-progress`, `/manage/search`,
  `/{id}/images`) need any authenticated account; `GET /api/artists/{name}/image` is public.
- **`rules.manage`**: `POST /api/artists/{id}/image/url`, `/image/upload`, `/image/select/{image_id}`,
  `/image/clear`, `POST /api/artists/fetch-missing` (alias `/fetch-images`), `POST /api/artists/{id}/fetch-image`.
- `/image/url` accepts only http(s) URLs whose host resolves to public addresses (400 otherwise; each
  redirect hop is re-checked) and downloads at most 10 MB (413). `/image/upload` takes base64 of at most
  10 MB (413).

### ⚙️ Configuration (`config.manage`)
- **GET `/api/config/fields`**: The schema: per field `key`, `type`, `group`, `description`, `nullable`, `default`, `secret`, `read_only` and the current `value`. A secret that is set reads as the sentinel (eight `•`), an unset one as its empty value.
- **GET `/api/config/`**: `{"config": {<key>: <value>}, "groups": [...]}`, secrets masked the same way.
- **POST `/api/config/`**: Body `{"updates": {<key>: <value>}}`. The whole payload is validated before anything changes: an unknown key, an unparsable value or a changed `read_only` field (the `db_*` database settings, which come from the environment) is a 400. A secret posted as the sentinel is left untouched. Response: `{"status": "success", "config": {<key>: <public value>}}` for every posted key -- **masked like the GET**. Until 0.72 this echoed each secret back in the clear. Only keys that differ from their environment value or default are persisted; see "Runtime Configuration" in `AGENTS.md` for the precedence.

### 🖼 Artist images
- **POST `/api/artists/{artist_id}/image/clear`**: Unsets the primary image (files and image rows are kept) and sets `image_status = 'cleared'`. The start-up bulk run and `/fetch-missing` skip a `cleared` artist; before this status existed the clear set `none` and the next restart fetched the portrait again.
- **POST `/api/artists/{artist_id}/fetch-image`**: Looks up a new portrait in the background. Skips a `cleared` artist unless `?force=true`; the manager's "search automatically" button sends `force=true`.
- **POST `/api/artists/fetch-missing`** (alias `/fetch-images`): Background run over every artist without an image, excluding `cleared` ones and `failed` ones inside the retry window (`ARTIST_IMAGE_RETRY_AFTER_DAYS`, default 30).
- `image_status` values: `active`, `failed`, `cleared`, or empty (never decided).

### ❤️ Health
- **GET `/health`**: Reports actual service health instead of a hard-coded `ok`. Response: `{"status": "ok"|"degraded", "service": "music-manager", "version": <string>, "database": "ok"|"unreachable", "threads": {"tagger": <bool>, "scanner": <bool>, "radio": <bool>, "news": <bool>, "events-retention": <bool>, "scrobble-rematch": <bool>, "song-versions": <bool>, "feeds-refresh": <bool>, "lms-db-sync": <bool>, "events": <bool>}, "heartbeats": {"<loop>": {"alive": <bool>, "stale": <bool>, "last_tick_age_seconds": <float|null>, "stale_after_seconds": <float|null>, "ticks": <int>, "failures": <int>}}}`. `database` is the result of `SELECT 1` on a dedicated short-lived connection, bounded at about 2 s, so the endpoint always answers. `threads` covers the long-running background loops plus the event worker; a loop is `true` only when its thread is alive and its last completed tick is younger than its staleness window (three intervals with a one-hour floor; tagger 24 h, scanner 12 h, news 3 h), counted from startup. One-shot startup tasks are deliberately excluded, since registering them would pin the endpoint to `degraded` within a minute of every restart. `status` is `degraded` — and the HTTP status code is 503 — when the database is unreachable or any of those threads has died or gone stale.
- **Any endpoint — 503 `{"detail": "No free database connection: the pool is exhausted"}`** with `Retry-After: 5`, when every pooled database connection stayed busy for `DB_POOL_WAIT_SECONDS` (default 5). Before, such a request waited forever.

### 📚 Library track lists
- **GET `/api/library/tracks`**: newest-first track list, `?q=` searches title, artist and label.
  `page` starts at 1 and `limit` (default 50) is capped at 500; `page=0`, a negative page or a larger
  `limit` is a 422 (it used to be a 500 from a negative `OFFSET`). Rows no longer carry `sc_url` /
  `yt_url`: those were two correlated `LIKE '%<basename>%'` scans of the download archives per row, and
  no client read them. `GET /api/library/tracks/by-path` and `POST /api/library/tracks/{id}/redownload`
  still resolve a track's source URL.
- **GET `/api/library/advanced`**: the filtered library browser list. Same paging bounds: `page` from 1,
  `limit` (default 100) at most 500, otherwise 422.

### 📥 ListenBrainz import
- **POST `/api/scrobble/import/listenbrainz`**: body `{"username", "lb_username"?, "token"?}`. Imports
  into `username`'s history, so an ordinary account may only name itself (403 otherwise); an admin or
  the system key may name anyone.
- **GET `/api/scrobble/import/latest`**: the last ten import rows. `status` is one of `pending`,
  `running`, `completed`, `truncated` or `failed`. A run fetches at most 100 pages of 100 listens; one
  that stops at that cap ends as `truncated` (it used to report `completed`). `oldest_listened_ts` is
  the Unix timestamp of the oldest listen a run reached; the next import for the same
  `username`/`lb_username` after a `truncated` or `failed` run continues strictly below it.

### 📻 News bulletins
See [news-mode.md](news-mode.md).
- **GET `/api/news/sources`**, **GET `/api/news/bulletins?source=&limit=`** (limit 1–100),
  **GET `/api/news/bulletins/latest?source=`** (404 when nothing is recorded yet): any authenticated
  account.
- **GET `/api/news/bulletins/{id}/stream`**: the audio, with `Range` support. A range that selects no
  byte of the file — start past the end, `start > end` such as `bytes=10-5`, or `bytes=-0` — is a 416
  with `Content-Range: bytes */<size>`; it used to produce a negative `Content-Length`.
- **POST `/api/news/sources`**, **PUT `/api/news/sources/{slug}`** (`news.manage`): out-of-range
  settings are a 422 — `minute_of_hour` 0–59, `duration_seconds` 60–3600, `lead_seconds` 0–300,
  `retention_count` 1–1000, `name` 1–128 and `stream_url` 1–512 characters.
- **DELETE `/api/news/sources/{slug}`** (`news.manage`): removes the source, its bulletin rows and their
  audio files; a file that cannot be deleted is logged, not an error.
- **POST `/api/news/sources/{slug}/record-now`** (`news.manage`): starts a capture in the background and
  answers at once; 409 while that source is already recording.
