# Authentication — Technical Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This
implements the already-agreed [functional.md](functional.md). Implemented in
`services/music_manager/routers/users.py`, `services/music_manager/routers/user_requests.py`, and
`services/music_manager/rbac.py`. See [Related Docs](#related-docs) for the deepest-detail reference.

## Data Model

`users` table (MariaDB, `music_management` database):

| Column | Required? | Notes |
|---|---|---|
| `id` | always present, auto-increment | the only field never chosen by the caller |
| `username` | `UNIQUE NOT NULL` at the DB level | auto-generated for Google-created accounts (`email`, or `google-<subject_prefix>` if no email) |
| `password_hash` | optional | `NULL` for a Google-only account; set for `/api/auth/setup` (first admin) or `POST /api/users` accounts |
| `email` | optional | always set for a Google-approved account (from the ID token claims); may be `NULL` for a local-only account |
| `role_id` | required, FK → `roles.name` (`admin`/`user`) | the only source of authorization; the legacy `is_admin` boolean is a read-only derived field (`role_name == 'admin'`), never written to directly and never checked for authorization |
| `enabled` | defaults `TRUE` | a disabled account can't log in (`403`) with either method |

**Invariant**: a user account is only reachable via login if it has *at least one* of `password_hash` set,
or a `user_identities` row (`provider='google'`). An account with neither exists but is currently
unreachable (see [Open Questions](functional.md#open-questions--not-yet-decided) in the functional design).

Related tables:

| Table | Purpose |
|---|---|
| `user_identities` (`user_id`, `provider`, `provider_subject`, unique per `(provider, provider_subject)`) | login-method-to-account mapping; currently only `provider='google'` |
| `user_requests` (`status`: `pending`/`approved`/`rejected`, `google_subject`, `email`, `display_name`, `reviewed_by_user_id`, `created_user_id`, `linked_existing`) | a pending/approved/rejected access request from an unrecognized Google identity |
| `user_refresh_tokens` | long-lived tokens issued alongside the `api_key` access token |
| `audit_events` | append-only log of `user_request.*` / `user.*` actions |

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `POST /api/auth/login` | `{username, password}` — `password` may be either the account's real password (checked against `password_hash`) or its current `api_key` (checked with a constant-time compare); the latter lets a Google-only/Google-linked account authenticate Subsonic/LMS calls (LMS forwards its own login attempts here, see `MusicManagementPasswordService.cpp`) without ever knowing a real password, since `AuthOverlay.svelte`'s Google flow only ever learns the `api_key` | `200 {api_key, refresh_token, user}` | `401` unknown username or wrong password/api_key (same generic message for all three, to avoid username enumeration); `403` account disabled |
| `POST /api/auth/google` | `{id_token}` (Google ID token) | `200 {status: "unknown", google: {...}}` if no identity/request exists; `200 {status: "request_<status>", request: {...}}` if a request already exists; `200 {api_key, refresh_token, user}` if the identity is linked and enabled | `404` linked user no longer exists; `403` account disabled |
| `POST /api/auth/access-request` | `{id_token}` | `200 {request: {...}}` (idempotent per Google subject — returns the existing request instead of creating a duplicate) | — |
| `GET /api/user-requests` | requires `user-requests.read` | list of requests | `403` missing permission |
| `POST /api/user-requests/{id}/approve` | requires `user-requests.approve`; body: `{link_user_id?: int, display_name?: string}` | `200 {request: {...}}` — creates a new `user`-role account (never `admin`) if `link_user_id` is omitted, or adds a `user_identities` row to the given existing account if provided; `display_name` overrides the account's display name either way | only allowed while `status = 'pending'` |
| `POST /api/user-requests/{id}/unapprove` | requires `user-requests.unapprove`; body: `{}` | `200 {request: {...}}` — request returns to `status = 'pending'` | only allowed while `status = 'approved'`; deletes the created account if `linked_existing = false`, or only removes the `user_identities` row if `linked_existing = true` |
| `POST /api/user-requests/{id}/reject` | requires `user-requests.reject` | `200 {request: {...}}` — `status = 'rejected'` | only allowed while `status = 'pending'` |
| `DELETE /api/users/{id}` | requires `users.update` (or the caller deleting their own account) | `200 {status: "ok"}` | `400` "Kan de laatste beheerder niet verwijderen" (refuses to delete the last admin); `404` user not found; `500` "Verwijderen mislukt: ..." on unexpected failure instead of a bare `500` |

## Cross-App Impact

`music-management-server` (LMS) does not store its own Subsonic passwords: every Subsonic/OpenSubsonic login
attempt (`u=`/`p=`) is forwarded live, in real time, to `POST /api/auth/login` by
`MusicManagementPasswordService` (`services/music-management-server/src/libs/services/auth/impl/musicmanagement/`)
and only succeeds if that call returns `200`. This means the frontend's `credentials` store
(`services/frontend/src/lib/store.js`), which every Subsonic call (genres, albums, streaming, ...) is built
from, must always hold a `{username, password}` pair this endpoint accepts — for a Subsonic/MuMa
username+password login that's the account's real password (`AuthOverlay.svelte`'s `verifyLogin`); for a
Google sign-in, which never learns a real password, `AuthOverlay.svelte`'s `handleGoogleResponse` instead
populates `credentials` with `{username: user.username, password: api_key}`, relying on `/api/auth/login`'s
`api_key` fallback above. Without this, a Google-signed-in user authenticates fine against `music-manager`
(gets a session, permissions, admin badge, ...) but every Subsonic call fails as unauthenticated, since LMS
has no username/password to forward. Ultrasonic authenticates the same way but always uses a real
username/password the user typed into the app, so it is unaffected by this.

## Technical Acceptance Criteria

1. `POST /api/auth/login` returns the identical `401` body for "username does not exist" and "wrong
   password", verified by a test for each case.
2. `POST /api/auth/google` returns `status: "unknown"` (not an error) the first time an unrecognized Google
   subject signs in, and `status: "request_pending"` (etc.) on a second attempt after a request already
   exists, without creating a second `user_requests` row.
3. `POST /api/user-requests/{id}/approve` with `link_user_id` set never inserts a new row into `users`; it
   only inserts into `user_identities`.
4. `POST /api/user-requests/{id}/unapprove` on a request with `linked_existing = false` results in the
   created account no longer existing in `users`; on a request with `linked_existing = true`, the
   pre-existing account still exists with all its other data untouched, and only its Google
   `user_identities` row is gone.
5. `DELETE /api/users/{id}` on the last remaining `admin`-role account returns `400`, and the account still
   exists afterward.
6. `DELETE /api/users/{id}` on a valid, non-last-admin account removes all of its `user_identities`,
   `user_refresh_tokens`, `dynamic_playlists`, `user_app_settings`, and `user_listenbrainz_accounts` rows,
   and nulls any `user_requests.reviewed_by_user_id` / `created_user_id` referencing it, rather than failing
   with a foreign-key constraint error.
7. All of the above are covered by tests in `services/music_manager/tests/test_users.py` and
   `services/music_manager/tests/test_rbac.py` (per AGENTS.md rule 1).

## Related Docs

- [docs/authentication.md](../../authentication.md) — the original, code-verified deep-detail reference this
  design was derived from; consult it for the full table-by-table breakdown if this summary is insufficient.
- [docs/designs/authentication/functional.md](functional.md) — the functional design this technical design
  implements.
