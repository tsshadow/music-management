# Account Settings Blob: The Last Writer Wins For The Whole Blob

# status: fixed

# reported problem
GitLab issue #39, left open by [bug report 041](041-web-player-keeps-the-previous-users-state.md).
The settings that follow an account -- favourite genres, labels and playlists, the interface
language, the home-screen counts, the track page size, set resume positions -- live in one JSON
blob per account (`user_app_settings`, `app_id = 'frontend'`). The web player writes it, and so
does the Android app natively (favourite genres, the one-off bookmark migration into `setResume`).
With the web player open on a laptop and the app on a phone or tablet, a change made on one device
could vanish when another device saved at about the same moment.

# Possible reason
`POST /api/users/{id}/settings/{app_id}` only accepts the whole blob and stores it with
`INSERT ... ON DUPLICATE KEY UPDATE settings_json = VALUES(settings_json)`. So every writer has to
read the blob, change its keys and post everything back:

- the web player (`writeSettingsBlob` in `services/frontend/src/lib/store.js`) read, merged its
  pending keys and posted;
- the app (`FavoriteGenres.push`, `BookmarkMigration.runOnce`) did the same through
  `getMumaSettings` + `saveMumaSettings`.

Bug report 041 made the web player batch its own writes and serialise them, which closed the race
between two keys inside one browser. It could not close the race between devices: device A reads,
device B reads, A posts, B posts a copy without A's change. The server had no way to write one key.

# solution
A per-key write, additive to the existing contract (design:
[docs/designs/account-settings-merge/](../designs/account-settings-merge/functional.md)):

- **Server**: `PATCH /api/users/{user_id}/settings/{app_id}` with `{"set": {...}, "remove": [...]}`
  sets and removes top-level keys and leaves every other key as stored. The read-merge-write runs
  in one transaction with `SELECT ... FOR UPDATE`, so a second writer waits and then merges into a
  blob that already holds the first writer's keys. Concurrent first writes of a missing row (gap
  lock deadlock or duplicate key) are retried up to three times. The user check before the lock is a locking read (`LOCK IN SHARE MODE`): a plain read there opened a read view that MariaDB 11.6+ snapshot isolation then refused the locked read against with error 1020 -- the first push of this fix failed its own concurrency test in CI that way. Answers the merged blob and its
  `updated_at`. `POST` and `GET` are unchanged, so older app versions keep working.
- **Web player**: the write queue sends `PATCH {"set": <pending keys>}` and no longer reads first;
  on 405 (a server without the PATCH) it falls back to the old read-merge-POST.
- **App**: `patchMumaSettings` with the same 405 fallback. Favourite genres send only
  `favoriteGenres`; the bookmark migration still reads `setResume` to keep newer entries but sends
  only that key.

Tests: `PatchAppSettingsTest` and `MergeSettingsBlobTest` (unit),
`test_two_concurrent_partial_writes_both_survive` and `test_many_concurrent_first_writes_all_survive`
in `tests/integration/test_router_sql.py` against a real MariaDB (the first holds the row lock from a
third connection so both PATCHes are provably in flight; with the `FOR UPDATE` removed it fails --
MariaDB 11.6+'s snapshot isolation answers the second write with error 1020 instead of losing it
silently), the store write-queue vitest suite, `FavoriteGenresTest`, `BookmarkMigrationTest` and
`MumaSettingsChangesTest`, plus a PATCH line in `scripts/test/reverse-proxy-routing.sh`.

Still last-writer-wins, by decision: two devices writing *the same* key, including two different
set positions inside the one `setResume` key.
