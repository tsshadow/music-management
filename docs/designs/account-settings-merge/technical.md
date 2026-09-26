# Account Settings Merge — Technical Design

Implements [functional.md](functional.md). GitLab issue #39,
[bug report 116](../../bug-reports/116-account-settings-blob-last-writer-wins.md).

## Data Model

No schema change. `user_app_settings` stays as it is: one row per `(user_id, app_id)` (unique key),
`settings_json LONGTEXT`, `updated_at` with `ON UPDATE CURRENT_TIMESTAMP`. The blob keeps being a
JSON object string; the merge happens in Python, not in SQL.

Why not `JSON_SET`/`JSON_MERGE_PATCH` in MariaDB: MariaDB's `JSON` is an alias for `LONGTEXT` and
its JSON functions return `NULL` for a blob that is not valid JSON -- which would silently wipe a
broken blob instead of treating it as empty, the rule the web player already follows. Building a
`JSON_SET` path per key also needs every key escaped into JSONPath syntax (the `setResume` map keys
are `work:<id>`). `JSON_MERGE_PATCH` merges nested objects recursively, which is not the semantics
the clients want (see below). A locked read-merge-write keeps the rule in one readable function.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `PATCH /api/users/{user_id}/settings/{app_id}` (new) | `{"set": {<key>: <any JSON>}, "remove": ["<key>"]}`, both optional (default empty) | `{"status": "ok", "settings": "<merged JSON string>", "updated_at": "<timestamp>"}` | 403: another user's blob without `users.update`. 404: unknown user. 422: a key in both `set` and `remove`; `set` not an object; `remove` not a list of strings. 500: database unavailable, or a collision that persisted through three attempts. |
| `POST /api/users/{user_id}/settings/{app_id}` (unchanged) | `{"settings": "<JSON string>"}` | `{"status": "ok"}` | unchanged |
| `GET /api/users/{user_id}/settings/{app_id}` (unchanged) | -- | `{"settings": ..., "updated_at": ...}` | unchanged |

Semantics of the PATCH:

- **Top-level, replace-per-key.** Each value in `set` replaces its key's stored value whole; nested
  objects are not merged. This is what both clients already did client-side (`{...current,
  ...changes}` in `store.js`, `root.add(key, ...)` in Kotlin), so switching to the PATCH changes
  nothing about the resulting document except that unrelated keys are no longer carried along.
  An RFC 7396 merge patch would have merged `setResume` recursively and made it impossible to drop
  an entry (the web caps that map at 50 entries) without sending explicit `null`s.
- **Removal is explicit** (`remove`), so `null` stays an ordinary value.
- A stored blob that is missing, not valid JSON or not a JSON object counts as `{}`.
- **Atomicity.** One transaction (`database.transaction`): `SELECT id FROM users ... LOCK IN
  SHARE MODE` (404), then `SELECT settings_json ... FOR UPDATE`, merge, `UPDATE` (or `INSERT` when
  there is no row), then read `updated_at` back. A second writer of the same row blocks on the
  `FOR UPDATE` until the first commits and then reads the blob with the first writer's keys in it.
- **No plain read before the row lock.** MariaDB 11.6+ runs with `innodb_snapshot_isolation=ON`:
  a transaction whose read view is older than a row version it then locks is refused with error
  1020 ("record has changed since last read"). A plain `SELECT` opens that read view, so the first
  version -- a plain user check before the `FOR UPDATE` -- failed exactly the concurrent case under
  the CI integration suite. The user check is therefore a locking read too (which also keeps the
  user from being deleted under the INSERT), and 1020 is on the retry list as a backstop.
- **First writes.** Two PATCHes against a row that does not exist yet both take its gap lock and
  collide on the INSERT: MariaDB answers one with a deadlock (1213) or a duplicate key (1062). These
  and 1020 are retried from the top, up to three attempts; by the second the row exists and the row
  lock serialises them. A lock wait timeout (1205) is not retried -- it has already waited
  `innodb_lock_wait_timeout`.
- **No version/ETag check.** An optional per-blob `If-Match`/`updated_at` precondition was
  considered and left out: with per-key writes it would reject a write for a *different* key that
  another device changed meanwhile -- re-creating the conflict this change removes -- and
  `updated_at` has one-second resolution. Two writers of the *same* key remain last-writer-wins,
  which is the accepted behaviour (functional flow 3). A per-key version can be added later without
  breaking the contract (an optional field).

This is **additive**: no existing request or response changed, so no client breaks (AGENTS.md
rule 10).

## Cross-App Impact

- **music-manager**: new route in `services/music_manager/routers/users.py`
  (`patch_user_app_settings`, `merge_settings_blob`).
- **Web player** (`services/frontend/src/lib/store.js`): the write queue sends `PATCH {"set":
  <pending changes>}` without reading first. On 405 (a server without the PATCH) it falls back to
  the old read-merge-POST, which still refuses to write after a failed read. The queue, debounce,
  retry and serial flush chain stay. `setResume.js` still reads the `setResume` map, adds its entry
  and saves that one key: merging *inside* a key is out of scope (functional.md).
- **MuMa Mobile**: `MumaAPIDefinition.patchSettings` (`@PATCH`), `MusicService.patchMumaSettings`
  (REST with the same 405 fallback, offline no-op, cached delegate). `FavoriteGenres` writes
  `{"favoriteGenres": [...]}` without reading first; `BookmarkMigration` still reads the blob (to
  keep newer `setResume` entries) but writes only `{"setResume": {...}}`. The web UI inside the app
  shell uses `store.js`, so it gets the PATCH with the web change; Capacitor's native HTTP bridge
  (`CapacitorHttp`, `HttpURLConnection` on Android) supports `PATCH`, and music-manager's CORS
  already allows it.
- **nginx**: behind the production reverse proxy `/muma/api/users/...` goes straight to
  music-manager (`services/music-management-server/nginx/reverse-proxy.conf`);
  `scripts/test/reverse-proxy-routing.sh` now pins that PATCH is forwarded.
- **LMS** (`MumaResource.cpp`, `core::http`): wherever LMS is reached without that proxy -- the
  test stack, a direct `lms.<domain>` -- `/muma/api/...` goes through LMS's generic MuMa proxy,
  which only forwarded GET, POST, PUT and DELETE. A PATCH fell through every branch, sent nothing,
  and parked the Wt thread and a MuMa call slot on an unfulfilled promise for 30 s before a 504;
  in `frontend:e2e` that starved the management pages behind it (spinners that never cleared). The
  HTTP client gained `sendPATCHRequest` (Wt's `Client::patch`), the proxy forwards PATCH, and any
  other verb now gets an immediate 405 instead of the 30 s wait. `HttpClient.eachVerbReachesTheServerAsItself`
  checks PATCH arrives as PATCH. LMS's own `/muma/users/{id}/settings/{app}` bridge still knows
  only GET and POST; no current client writes through it.

## Technical Acceptance Criteria

1. `PATCH` with `set` changes exactly those keys; every other stored key is byte-for-byte the same
   value (unit: `PatchAppSettingsTest`; integration: `test_a_settings_patch_changes_only_the_named_keys`).
2. `remove` deletes keys; a key in both lists is a 422 before any SQL runs.
3. A missing row is inserted; a broken blob counts as empty (`MergeSettingsBlobTest`).
4. The read is `FOR UPDATE` inside one transaction; two concurrent PATCHes of different keys both
   survive against a real MariaDB, with a third connection holding the lock so both are in flight
   (`test_two_concurrent_partial_writes_both_survive`); six concurrent first writes all survive
   (`test_many_concurrent_first_writes_all_survive`). Without `FOR UPDATE` the first test fails.
5. A deadlock is retried; a collision that persists fails after three attempts; other errors are
   not retried.
6. The web player sends only its pending keys, never reads before writing, and falls back to the
   old write on 405 (vitest, `store.test.js`).
7. The app's favourite-genres and bookmark-migration writes carry only their own key
   (`FavoriteGenresTest`, `BookmarkMigrationTest`); the fallback merge replaces only the changed
   top-level keys (`MumaSettingsChangesTest`).
8. POST and GET are unchanged (existing tests).

## Related Docs

- [Bug report 041](../../bug-reports/041-web-player-keeps-the-previous-users-state.md): the client-side
  write queue this builds on.
- [docs/api-specification.md](../../api-specification.md), "Users".
