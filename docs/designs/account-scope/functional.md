# Account scope of the import list and account deletion — Functional Design

## Overview

Bug report 052 left two account-scope questions open, and GitLab issue #38 decided both: they go
behind the admin role. The list of recent ListenBrainz imports showed every account's imports
(name, ListenBrainz name, error text) to anyone signed in, and a plain account could delete itself
with a single API call.

## User Stories

- As a listener, I want my ListenBrainz imports, and the errors they hit, to stay mine.
- As an admin, I want to keep seeing every import, so I can help when one fails.
- As an admin, I want deleting an account to be my decision, so nobody loses their account, ratings
  and history through one mistaken call.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Admin opens Beheer > Scrobbles | The ten newest imports of every account, as before. |
| A plain account asks for the import list (API) | Only its own ten newest imports. |
| Admin deletes another account in Beheer > Gebruikers | Deleted, as before. |
| Admin deletes the last enabled admin | Refused; the reason the server gives ("laatste beheerder") is shown instead of a generic error. |
| A plain account tries to delete itself (API) | Refused (403); nothing changes. |

## Acceptance Criteria

1. A plain account never sees another account's import rows.
2. An admin (and the system key) sees every account's rows.
3. Only an account with `users.update` (admins by default) can delete an account, its own included.
4. The last enabled admin still cannot be deleted.

## Open Questions / Not Yet Decided

- None.
