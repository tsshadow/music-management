- **The last admin could demote or disable itself.** Only `DELETE /api/users/{id}` refused to remove
  the last admin, and it counted disabled admins as spares. `PUT /api/users/{id}/role` and
  `POST /api/users/{id}/disable` now share its check, which counts only *other enabled* admins, and
  all three answer `409` (delete answered `400`). Bug report 052.
- **Two simultaneous first-time setups could create two admins.** `POST /api/auth/setup` counted the
  users and then inserted without a lock. The check and the insert now run under a lock and the
  `INSERT` itself refuses a non-empty table; the loser gets `409 Setup already completed` (was `400`).
- **Login timing told whether a username existed.** An unknown username was answered before bcrypt
  ran -- milliseconds against a quarter second. It now pays for one bcrypt check against a dummy
  hash and gets the same text as a wrong password; "Account disabled" only follows a correct password.
- **A database outage read as "Invalid API key".** The `library` and `scrobbler` routers kept their
  own key check, which swallowed every exception into a `401`. They now delegate to
  `users.verify_api_key`, and `verify_token` answers `503` when the users table cannot be read
  (before: `403 Invalid API Key` without a pool, `500` on a connection error).
- **Any account could scrobble into another account's history.** `POST /api/scrobble/event` took
  the body's `username` at its word for every key. A user key may now only name itself (`403`
  otherwise); admins and the system key, which LMS uses, still name anyone.
- **`user_refresh_tokens` grew without bound.** Every successful login -- including every LMS
  Subsonic password check it has not cached -- inserted a row that was never removed. Each account
  now keeps its 10 newest, pruned on issue, and the daily `events-retention` pass applies the same
  cap everywhere and drops revoked rows older than 30 days.

<!-- release notes -->

- **Accounts and login:** the last active admin can no longer be demoted or disabled, first-time
  setup can no longer produce two admins, login no longer reveals whether a username exists, and a
  database outage now reads as an outage (503) instead of "invalid API key". Listens can only be
  written to your own history, and old refresh tokens are cleaned up.
