- **A disabled or deleted MuMa account no longer keeps streaming through LMS.** The user sync only
  ever created and updated LMS users, so an account disabled in MuMa kept its Subsonic key and every
  client holding it went on playing. The next sync now disables the LMS user (new `user.disabled`
  column, LMS migration step 121, database version 122) and revokes every auth token it holds, in
  every domain. The same happens to an LMS user whose MuMa account has gone from the list. The user
  is disabled, never deleted: listens, ratings, stars and playlists refer to it by id and stay where
  they are, ready for a re-enabled account. No credential lets a disabled user in -- token, salted
  token, password or proxy header -- including a token issued after the sync. An empty user list,
  or one with an unreadable id, disables nobody as deleted. `DELETE /api/users/{id}` now pokes the
  LMS sync after its commit, as enable and disable already did, so a deleted account is locked out
  at once instead of at the next sync.
- **One bad row no longer ends the LMS user sync.** A row without a username, or one whose write
  failed (two LMS users claiming the same MuMa id), ended the loop, and every account after it went
  unsynced until the next sync. Each account is now written in its own transaction: an unusable row
  is logged and skipped and the rest are applied.
- **The LMS fork is documented.** `services/music-management-server/FORK.md` records the upstream
  base (LMS v3.76.0, `d3eb168d7`; the `3.83.1` project version is the fork's own), the MuMa-specific
  subsystems, how upstream fixes are ported, and the database version policy: steps from 103 up are
  the fork's own sequence, and an upstream migration is ported under the next free step, never merged
  under its own number (upstream's 103-115 already mean something else here).
- **New C++ tests** for the MuMa listen and rating relays (payload, key header, how the send queue
  retries and drops them), the user sync, disabled-user authentication and the `/muma` routing
  helpers (allow-list, settings path, proxied URL and headers), now in `Routing.cpp`. A settings
  path whose user id is not a plain number (`12abc`) is a 400; it used to be read as user 12.

<!-- release notes -->

- **Disabling or deleting an account in MuMa now also locks it out of the music server.** Its
  history and ratings are kept, and come back if the account is enabled again.
