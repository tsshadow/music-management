# LMS fork baseline and account lifecycle — Functional Design

## Overview

The music server (`services/music-management-server`) is a hard fork of the open-source LMS. Until
now nothing in the repository said which LMS release it started from, which parts are MuMa's own,
or how an upstream fix could be brought in without breaking the database. That is written down in
[`services/music-management-server/FORK.md`](../../../services/music-management-server/FORK.md).

The same audit (C9) found a gap in how accounts reach the music server. MuMa owns the accounts and
tells the music server about them through a user sync, but the sync only ever created and updated
users. Disabling or deleting an account in MuMa did nothing on the music server: the Subsonic key
on the phone kept working. And one malformed account in the list stopped the sync for every account
after it.

## User Stories

- As the administrator, I want disabling an account in MuMa to lock it out of the music server too,
  so that a key on a lost phone or a departed user's device stops working.
- As the administrator, I want a disabled account's listening history and ratings kept, so that
  re-enabling the account gives it back everything it had.
- As the administrator, I want one broken account in MuMa not to keep every other account from
  being synced.
- As a developer, I want to know where the fork started and how to port an upstream fix, so that a
  port does not collide with the fork's database migrations.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| An account is disabled in MuMa | MuMa pokes the music server's user sync right after the change; from then on the music server refuses that user's Subsonic key, password and web session. |
| An account is deleted in MuMa | Same as disabled, and the LMS user is renamed to `deleted-<id>`, so a new account with the name starts empty. MuMa pokes the sync after the delete. |
| A disabled account is enabled again | The user can sign in again. Its listening history, ratings, stars and playlists are all still there. Clients need a new Subsonic key: the old ones were revoked. |
| MuMa's user list has one malformed row | That row is skipped and logged; every other account is synced. |
| MuMa answers with an empty list or an error | Nobody is disabled. |

## Acceptance Criteria

1. After disabling an account in MuMa, a Subsonic request with that account's old key is refused.
2. Signing in to the music server's web UI with that account's password is refused.
3. Re-enabling the account in MuMa lets it sign in again, with its ratings and history intact.
4. Deleting an account in MuMa has the same effect as disabling it; the music server keeps the
   user's data.
5. A user list with one bad row still syncs every other account.
6. `FORK.md` names the upstream base release and commit, lists the MuMa-specific parts, gives the
   database version policy and a porting procedure.

## Open Questions / Not Yet Decided

- None. Whether a disabled user should also disappear from the music server's own admin user list
  was left out: the admin UI is not used for MuMa accounts.
