## 🔌 API Specification

The `music-manager` service provides a REST API (FastAPI) for managing the music library, users, and events.

### 🔐 Authentication
- **POST `/api/auth/login`**: Authenticate with username/password and receive the user's own API
  key: `200 {status, api_key, access_token, refresh_token, user}`, `user` carrying `permissions`,
  `role_name` and `is_admin`. The username matches in any case, and `user.username` is the account's
  own spelling, which clients sign in under afterwards (see `docs/authentication.md`, "Account names
  are case-insensitive"). `POST /api/users` answers `409` for a case variant of an existing name.
  The web player reaches it as `/muma/api/auth/login` (nginx, or LMS's
  pass-through when LMS is reached directly); LMS no longer answers that path itself with its own
  `api-key` (breaking for any client that read LMS's flat `{id, username, is_admin, api_key}`). The
  session endpoints (`/api/auth/*`) and `GET /api/roles` are the only `users` routes under the bare
  `/api` prefix; every other user route is under `/api/users` only (there is no `/api/{user_id}/...`,
  and no `/api/users/auth/*`).
  An unknown username and a wrong password both answer `401 Invalid username or password`, at the
  same bcrypt cost; `403 Account disabled` only follows a correct password.
- **GET `/api/auth/verify`**: Verify the validity of an `X-API-Key`. 401 without a key, 403 for an
  unknown key or a disabled account, 503 (`Retry-After: 5`) when the users table cannot be read.
- **GET `/api/auth/subsonic-token`**: the caller's own Subsonic API token, issued into LMS's
  `lms.db` on first request, as `{status: "ok", username, token}` -- `username` is LMS's login name
  for the account, which is what `u=` must carry. Clients sign every `/rest` call with
  `t=md5(token + salt)&s=salt` instead of `p=` (bug report 103). Only a user key: no key or an
  unknown key 401, a disabled account 403, a system key 403 (a service has no token of its own). No
  parameter can name another account. 404 when no server database knows the account yet, 503 when
  music-manager sees no server database or cannot read it (`Retry-After: 5`). The key check counts
  towards the login rate limit (429 with `Retry-After`). An administrator-issued token is returned
  as it is; see [docs/designs/subsonic-token-signing/technical.md](designs/subsonic-token-signing/technical.md).
- **POST `/api/auth/setup`**: create the first account, as admin, while no account exists. `409 Setup
  already completed` once one does (was 400); concurrent calls create exactly one admin.

Every route below takes the key in `X-API-Key` and resolves it through the one
`routers.users.verify_api_key` (401 without a key or for a key no account holds, 403 for a disabled
account, 503 when the database cannot be asked -- no router answers "Invalid API key" for an outage
any more). `GET /api/auth/verify` itself still answers 403 for an unknown key. "Admin"
means the admin role (`rbac.require_admin`); a named permission means `rbac.require_permission`.
The system key passes every check. Routes not marked otherwise need any authenticated account.

### ⏳ Deprecated (removal on 2026-11-01)
No consumer was found in this repository for these routes (web player, MuMa Mobile, LMS, scripts,
tools, tests/contracts -- see
[docs/bug-reports/084-unused-endpoints-and-duplicate-normalizers.md](bug-reports/084-unused-endpoints-and-duplicate-normalizers.md)).
They still work unchanged, are flagged `deprecated` in the OpenAPI schema, and the first call per
route per process logs one `INFO` line (`music-manager.deprecation`, so it lands in `/api/events`)
naming the path and the caller's address. A route that has not shown up there by 2026-11-01 is
deleted; one that has is kept and gets a consumer entry in the bug report.
- `GET /api/about`
- `GET|POST /api/rules/artist-redirects`, `DELETE /api/rules/artist-redirects/{id}`
- `POST /api/tagger/rescan/file`
- `POST /api/songs/tracks/{track_id}/split`
- `GET /api/downloaders/schedule/{source}`
- `GET /api/users/permissions`
- `POST /api/users/sync/lms-db` (use `/api/users/sync/muma-server`)

Removed outright, because every caller already uses the target: `GET|PUT
/api/users/{user_id}/lb-account` (use `/listenbrainz`), `POST /api/users/sync/lms` (use
`/sync/muma-server`) and `POST /api/rating/server-event` (use `/lms-event`, which LMS calls).

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
  now 404. Enable, disable and delete each poke the music server's user sync (`/muma/users/sync`)
  after the commit; LMS disables a user whose account is disabled or gone from `GET /users/` and
  revokes its keys.
- **POST `/users/sync/muma-server`** (deprecated alias `/sync/lms-db`; `/sync/lms` removed): run the
  lms.db sync now and return `{"synced": <int>}`. Admin only; 409 while a sync (manual or the hourly
  loop) is running.
- **GET `/users/{user_id}/settings/{app_id}`**: Retrieve application-specific settings (e.g., `app_id=ultrasonic` for MuMa Mobile's settings backup, `app_id=frontend` for the web player's favorite genres).
- **POST `/users/{user_id}/settings/{app_id}`**: Backup application-specific settings.
- **GET `/users/{user_id}/listenbrainz`**: Get ListenBrainz integration details; `POST|PUT` stores
  them. (The `/lb-account` alias was removed with bug report 084.)

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
- **POST `/api/rating/lms-event`**: the LMS rating webhook (the `/server-event` alias was removed with
  bug report 084). System key
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
- **GET `/api/rules`**, `/api/artists`, `/api/labels`, `/api/label-proposals`, `/api/config`, `/api/about` (deprecated),
  `/api/stats`, the curation queues and the downloader account lists: any authenticated account.
- **`rules.manage`**: `POST /api/rules/genres/{id}/decide`, `POST /api/rules/podcasts/{id}/decide|rename`,
  `POST|DELETE /api/rules/podcasts/{id}/aliases`, `POST /api/rules/artist-genres`,
  `DELETE /api/rules/artist-genres/{id}`, `POST /api/rules/label-genres`, `DELETE /api/rules/label-genres/{id}`,
  `POST /api/rules/artist-redirects`, `DELETE /api/rules/artist-redirects/{id}` (both deprecated),
  `POST /api/label-proposals/{id}/confirm|reject`, `POST /api/tagger/rescan`, `POST /api/tagger/rescan/file`
  (deprecated).
- **GET `/api/import-conflicts`** (any authenticated account): the folder pairs the importer's renamer or
  mover left in place because the name it wanted is taken by a folder holding a different release
  (bug report 091). `[{step, source, target, first_seen, last_seen}]`, oldest first; `step` is `renamer`
  or `mover`, `source`/`target` are full paths. Read-only: a pair disappears on the importer's next cycle
  once one of the two folders was removed or renamed by hand.
- **Channel links** (`/api/channel-links`, docs/designs/channel-links/technical.md): proposals that link a
  SoundCloud/YouTube channel to its label or artist on strong name equality.
  - **GET `/proposals?status=new|confirmed|rejected|stale&kind=label|artist`** (any authenticated account):
    `[{id, channel_id, platform, channel_name, kind, target_id, target_name, source, status, track_count,
    created_at, decided_at}]`, busiest channel first. `source` is `name`, `alias` or `redirect`. `400` for an
    unknown status or kind.
  - **POST `/proposals/refresh`** (`rules.manage`): runs the search, `{created, open, withdrawn, ambiguous}`.
    Decided rows are never touched; a second run in a row reports `created: 0, withdrawn: 0`.
  - **POST `/proposals/{id}/confirm`** (`rules.manage`): writes `channels.label_id`/`artist_id`,
    `{status: "confirmed", channel_id, kind, target_id}`, or `status: "stale"` when the target was deleted.
    Idempotent. `404` unknown id, `409` when the proposal is rejected/stale or the channel is linked to
    another target of that kind.
  - **POST `/proposals/{id}/reject`** (`rules.manage`): `{status: "rejected"}`, idempotent; `409` on a
    confirmed proposal.
  - **DELETE `/channels/{channel_id}/{kind}`** (`rules.manage`): clears the link and rejects the proposal
    behind it, `{status: "unlinked"}`; `400` unknown kind, `404` unknown channel.
- **GET `/api/downloaders/coverage/{source}`**: each account row gained (additive) `channel`: `null` or
  `{id, name, label: {id, name}|null, artist: {id, name}|null, open_proposals}`, found through one archive
  path of the account. SoundCloud `last_download_at` is now looked up by `soundcloud_id` (bug report 089).
- **GET `/api/tagger/retag/pending`**: `{"total": <int>, "by_reason": [{"reason", "count"}], "failed": <int>,
  "busy": <bool>, "stopping": <bool>}`. `total` counts the queued files; `failed` (added, additive) counts
  the files parked after failing `TAGGER_PARK_AFTER` times in a row, which are not in `total` and wait
  until the file changes or a retag is requested (bug report 051).
- **GET|POST `/api/tagger/todo-label-repair`** (admin): one page of the `__TODO` label repair (bug
  report 087). Query `after` (cursor: the previous page's `next_after`), `limit` 1-2000 (default 300).
  Response `{mode, reason, roots, scanned, poisoned, by_area, by_field, by_label, poisoned_paths, undecidable_count,
  undecidable, queued, next_after, done}`. GET is a dry run and writes nothing; POST queues the page's
  poisoned files for the tagger with reason `todo_label_repair` and never retags inline. `422` for a
  bad `limit`; a database error is a `500`, never an empty page reported as `done`.
- **PUT `/api/curation/genres/{name}/parents`** (`rules.manage`): body `{"parents": [<genre>, ...]}`,
  replaces the genre's parents in `rules_subgenre_hierarchy`. `400` for a genre listed as its own parent
  or an unknown/unaccepted parent, `403` when curation has not accepted the genre itself, and `409` with
  detail `"<genre> is already an ancestor of <parent>"` when a parent sits below the genre (at any depth),
  since storing it would close a cycle. Nothing is written when any parent is refused (bug report 064).
- **GET `/api/curation/genres/{name}`**: the edit page's view -- `name`, `genre_id`, `state`, `editable`,
  `occurrences`, `hardness`, `parents`, `children`, and (added, additive) `descendants`: every genre below
  this one at any depth, the ones the page will not offer as a parent.
- **GET `/api/curation/genre-hierarchy/cycles`**: read-only integrity check, any authenticated account.
  `{"count": <int>, "cycles": [[<genre>, ...], ...]}`, one sorted member list per cycle (a genre that is
  its own parent is a one-member cycle). New cycles are refused by the `PUT` above; a stored one is
  fixed by removing a parent on the genre edit page in Beheer.
- **GET `/api/rules/artists`** (any authenticated account): `state` is one of `unknown` (the queue),
  `pending` (added, additive: the part of the queue the tagger does not trust -- undecided names that were
  not in the library when the queue was wired up), `white`, `black`, `all`. Every row carries (added,
  additive) `pending: <bool>`. **GET `/api/rules/artists/summary`** adds `pending`, the count of those names.
  See docs/designs/artist-curation/technical.md, "Wiring the queue".
- **POST `/api/rules/artists/decide`** (`rules.manage`): body `{"names": [...], "state": "white"|"black",
  "canonical_name": <string|null>}`. Response (fields `repointed` and `returned_to_queue` added, additive):
  `{"status": "ok", "decided": <int>, "canonical_name": ..., "repointed": [<name>], "returned_to_queue": [<name>]}`.
  Rejecting a name that other redirects point at settles them in the same transaction (bug report 080):
  with a `canonical_name` they are re-pointed to it (`repointed`); without one their decision is forgotten
  and they go back to the queue (`returned_to_queue`). A `canonical_name` that is rejected is a `400`.
- **DELETE `/api/rules/artists/{name}`** (`rules.manage`): forgets a decision; `404` when there is none
  (nothing is changed then). Both this and `decide` reload the tagger's trusted-artist snapshot, so an
  approval is recognised in titles and an undone name stops being so at once. Redirects that pointed at the
  name go back to the queue with it; response
  `{"status": "ok", "returned_to_queue": [<name>]}`.
- **GET `/api/rules/artists/redirects/issues`**: read-only integrity check, any authenticated account.
  `{"count": <int>, "dangling": [{"name", "target", "path", "reason"}], "cycles": [[<name>, ...]],
  "chains": [{"name", "path"}]}`. `dangling` is a redirect (from `rules_ignored_artists`, or an unmirrored
  `rules_artists` correction) whose final target is rejected, a plain drop row, or -- for a redirect made on
  the curation page -- has no decision any more. `cycles` are redirect loops. `chains` are redirects of
  more than one hop; the tagger follows those to the end since bug 080, so they are information and not
  counted in `count`. Fix a finding by deciding the name again on the Artiestcuratie page.
- **POST `/api/rules/artist-redirects`** (`rules.manage`): additionally `400` when `corrected_name` is
  rejected in `rules_artists`, or when the redirect would close a loop (a casing fix of the name itself is
  not a loop).
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

### 🎚 Song versions (`/api/songs`)
Which of a song's versions plays, and the Versions page in Beheer that corrects it
([docs/designs/song-versions/](designs/song-versions/technical.md)). Reads need an API key, writes
need `rules.manage`.
- **GET `/api/songs/curation?q=&sort=versions|changed|title&changed_only=&page=&page_size=`**: every
  song (work) with more than one version, paged (`page_size` at most 100, `422` above). `q` matches
  the title or the artist. `changed` sorts songs whose automatic choice the last rescore changed
  first, newest change first. Response `{"items": [{work_id, title, artist, version_count,
  canonical_track_id, canonical_title, pinned_track_id, previous_canonical_track_id,
  canonical_changed_at}], "total", "page", "page_size"}`. An unknown `sort` is a `422`.
- **GET `/api/songs/ranking`**: `{"signature": "v2-lossless", "prefer_lossless": true,
  "pending_works": <works still scored under another ranking>, "changed_works": <works flagged by a
  rescore>}`.
- **GET `/api/songs/{work_id}`**: one song and its versions, one entry per file, best score first:
  `track_id, title, version_kind, version_score, file_path, format, bitrate_kbps` (derived from size and
  length), `duration_secs, source` (`label|soundcloud|youtube|other`), `is_official, rating` (highest any
  user gave), `plays, is_canonical`; plus the song's `artist, canonical_track_id, pinned_track_id,
  previous_canonical_track_id, canonical_changed_at`. `404` for an unknown song.
- **POST `/api/songs/{work_id}/pin`** `{"track_id": int | null}`: pin a version as best, or `null` to
  reset to automatic. Clears the rescore flag. `404` unknown song or track, `400` a track of another
  song, `403` without `rules.manage` (since 2026-09-26; it accepted any API key before, and had no
  consumer outside tests).
- **POST `/api/songs/{work_id}/dismiss-change`**: accept what the rescore chose; clears the flag, keeps
  the canonical. `404` unknown song.

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
- **POST `/api/artists/{artist_id}/image/clear`**: Unsets the primary image (files and image rows are kept) and sets `image_status = 'cleared'`. The start-up bulk run and `/fetch-missing` skip a `cleared` artist; before this status existed the clear set `none` and the next restart fetched the portrait again. It also removes the published copies behind the fixed URL (`/media/artist-images/{id}/primary.jpg` and `thumb_<size>.jpg`), and the next server sync (start-up, then hourly) unsets the server's `preferred_artwork_id` when it still points at one of this artist's stored files -- artwork the server found itself is left alone (bug report 080).
- **POST `/api/artists/{artist_id}/image/select/{image_id}`**: Makes a stored image the primary one and republishes `primary.jpg`/`thumb_<size>.jpg` from it.
- **POST `/api/artists/{artist_id}/fetch-image`**: Looks up a new portrait in the background. Skips a `cleared` artist unless `?force=true`; the manager's "search automatically" button sends `force=true`.
- **POST `/api/artists/fetch-missing`** (alias `/fetch-images`): Background run over every artist without an image, excluding `cleared` ones and `failed` ones inside the retry window (`ARTIST_IMAGE_RETRY_AFTER_DAYS`, default 30).
- `image_status` values: `active`, `failed`, `cleared`, or empty (never decided).

### ❤️ Health
- **GET `/health`**: Reports actual service health instead of a hard-coded `ok`. Response: `{"status": "ok"|"degraded", "service": "music-manager", "version": <string>, "database": "ok"|"unreachable", "threads": {"tagger": <bool>, "scanner": <bool>, "radio": <bool>, "news": <bool>, "events-retention": <bool>, "scrobble-rematch": <bool>, "song-versions": <bool>, "feeds-refresh": <bool>, "lms-db-sync": <bool>, "events": <bool>}, "heartbeats": {"<loop>": {"alive": <bool>, "stale": <bool>, "last_tick_age_seconds": <float|null>, "stale_after_seconds": <float|null>, "ticks": <int>, "failures": <int>}}}`. `database` is the result of `SELECT 1` on a dedicated short-lived connection, bounded at about 2 s, so the endpoint always answers. `threads` covers the long-running background loops plus the event worker; a loop is `true` only when its thread is alive and its last completed tick is younger than its staleness window (three intervals with a one-hour floor; tagger 24 h, scanner 12 h, news 3 h), counted from startup. One-shot startup tasks are deliberately excluded, since registering them would pin the endpoint to `degraded` within a minute of every restart. `status` is `degraded` — and the HTTP status code is 503 — when the database is unreachable or any of those threads has died or gone stale.
- **Any endpoint — 503 `{"detail": "No free database connection: the pool is exhausted"}`** with `Retry-After: 5`, when every pooled database connection stayed busy for `DB_POOL_WAIT_SECONDS` (default 5). Before, such a request waited forever.
- **Any endpoint — 503 `{"detail": "Database unavailable"}`** with `Retry-After: 5`, when the connection pool could not be created at all (MariaDB unreachable at startup). The curation, festival, genre and artist rules, radio, news and songs routers used to answer this with a 500.

### 📚 Library track lists
- **GET `/api/library/tracks`**: newest-first track list, `?q=` searches title, artist and label.
  `page` starts at 1 and `limit` (default 50) is capped at 500; `page=0`, a negative page or a larger
  `limit` is a 422 (it used to be a 500 from a negative `OFFSET`). Rows no longer carry `sc_url` /
  `yt_url`: those were two correlated `LIKE '%<basename>%'` scans of the download archives per row, and
  no client read them. `GET /api/library/tracks/by-path` and `POST /api/library/tracks/{id}/redownload`
  still resolve a track's source URL.
- **POST `/api/library/tracks/{id}/redownload`**: fetches the track again from the archive's source URL
  and replaces the file in place, atomically (a failed download leaves the old file). The source is
  found by the exact stored path (SoundCloud archive `filename`, YouTube archive `path`) over every
  spelling of the library path; only when none matches, by the exact file name in the same folder (or
  in a row that recorded no folder). Response unchanged: `{"status": "ok", "message": ...}`. `404` no
  file for the track, `400` no archive knows it, `409` the file name matches more than one archived
  download and the path does not say which (it used to take the first `LIKE '%<name>%'` hit).
- **GET `/api/library/advanced`**: the filtered library browser list. Same paging bounds: `page` from 1,
  `limit` (default 100) at most 500, otherwise 422.
  Filters (shared with every `/api/analytics/*` endpoint, `routers/analytics_filters.py`): `form`
  (repeatable, OR; one of `track`, `set`, `liveset`, `podcast`, otherwise 422; a track not yet
  classified matches none) and `year_min`/`year_max`, which compare the year a track files under --
  a live set's `performance_date` first, then `library_tracks.release_date`, then the analyzer's
  `release_year` (docs/designs/track-form/).

### 🔁 LMS listen reconcile (admin)
Repairs listen times bug report 039 moved, from LMS's own `listen` table. Rules and the file-path
join are in the 2026-09-24 section of `docs/designs/ratings-scrobbling/technical.md`.
- **GET `/api/scrobble/reconcile/lms`**: dry run, writes nothing. `username` (optional) limits it to
  one user. Response `{username, servers, zones: {process_offset_seconds, database_offset_seconds,
  database_zone, consistent}, totals: {exact, shifted, muma_only, lms_only, lms_only_insertable,
  lms_unmapped}, users: {<username>: <same counts>}, sample: {shifted, muma_only, lms_only,
  lms_unmapped}}` (at most 20 rows per class). 403 for a non-admin, 503 when no `lms.db` is visible.
  `users` is keyed by muma's `users.username`: LMS and muma spellings that differ only in case
  count as one user. `servers` lists only databases with the core LMS schema; a stale `lms.db`
  without a `user`, `track` or `listen` table is left out, as it is for every LMS sync.
  `lms_only_insertable` counts LMS listens with no muma or unmatched listen of that user within
  600 s (the same play recorded by the app a minute after LMS saw it start).
- **POST `/api/scrobble/reconcile/lms`**: body `{"username"?, "apply_shifted": bool,
  "insert_lms_only": bool}`; at least one must be true (400 otherwise). Starts the apply in the
  background (409 while one runs); one transaction per user, UNIQUE collisions skipped and counted,
  refused when `zones.consistent` is false. Response `{message, last}`. Since bug report 075 the
  `lms-listen-backfill` loop inserts recent lost listens (last 48 h) by itself; this call with
  `insert_lms_only` is the one-off path for the older backlog, and the only way to apply `shifted`.
- **GET `/api/scrobble/reconcile/lms/status`**: `{running, last, error}`; `last` holds
  `{found, written: {shifted_fixed, lms_only_inserted, collisions, changed_since_read}, users, zones, ...}`.

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
