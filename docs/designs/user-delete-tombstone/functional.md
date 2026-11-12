# User Delete Tombstone — Functional Design

## Overview

music-manager keeps a person's ratings, listens, unmatched listens, ListenBrainz imports and feeds
under their username, not under their account id. A deleted account left all of them behind. A
new account with the same name then got the old ratings and listens.

Teun decided on 2026-11-12 to keep the history under a tombstone name (issue #220). The server
totals keep counting it, and the new account starts empty.

## User Stories

- As an admin, I want a new account with a reused name to start empty, so that it does not show
  another person's ratings and listens.
- As an admin, I want the library-wide totals to stay the same after a delete, so that play counts
  do not drop.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| An admin deletes account 12 "anna" | Her ratings, listens, imports and feeds move to `deleted-12`. |
| An admin makes a new account "anna" | It has no ratings, listens, imports or feeds. |
| Someone tries to make an account "deleted-12" | Refused (409), the name holds history. |
| The delete fails halfway | Nothing changes: the account and its history stay together. |

## Acceptance Criteria

1. After a delete and a new account with the same name, the new account has no ratings or listens.
2. The library-wide play and rating totals are the same before and after the delete.
3. No account can be made with a name `deleted-<number>`.

## Open Questions / Not Yet Decided

- The LMS user of a deleted account is disabled, not deleted, and LMS finds users by name. A new
  account with the same name gets the old LMS user back, with the listens and ratings LMS keeps.
  That is outside this change (follow-up issue).
