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
has no username/password to forward.

LMS's own `/muma` bridge (`MumaResource`) accepts the same two credentials and nothing weaker: a key only
once it matches LMS's `api-key` or MuMa confirms it through `GET /api/auth/verify` (the answer's `user.id`
and `user.is_admin` then name the caller), or a `u`/`p` pair through `MusicManagementPasswordService`. It
never takes the caller from the `u` parameter alone and its proxy never substitutes the system key for a
caller without one -- see [docs/authentication.md](../../authentication.md#the-lms-muma-bridge-mumaresource)
and bug report [056](../../bug-reports/056-lms-any-key-is-admin.md).

**MuMa Mobile** also supports native Google Sign-In (`EditServerFragment.startGoogleSignIn()`, Android
Credential Manager + `androidx.credentials`/`googleid`, via `GetSignInWithGoogleOption`). It reuses
`GOOGLE_CLIENT_ID`/`VITE_GOOGLE_CLIENT_ID`'s value as the Credential Manager `serverClientId`
(`GOOGLE_WEB_CLIENT_ID` build config field — see `docs/deployment.md`), so the resulting Google ID token has
the same audience the backend already verifies against. Unlike the web frontend, though, MuMa Mobile **does**
need a separate Android-type OAuth client (package name + signing certificate SHA-1) registered in the same
Google Cloud project — Google's Credential Manager backend refuses to issue a credential to a native Android
app otherwise, even though that Android client ID is never referenced in code (see bug report
[011](../../bug-reports/011-google-signin-no-credential-real-device.md) and `docs/deployment.md`'s "Google
Sign-In on MuMa Mobile (Android)" section for the two required client registrations, one per signing key).
`performMumaGoogleAuth()` mirrors `handleGoogleResponse()` exactly: on a `status:
"ok"` response, alongside storing the MuMa access/refresh token, it also writes `result.user.username`/
`api_key` into the server's Subsonic username/password fields (`userNameEditText`/`passwordEditText`/
`ServerSetting.userName`/`.password`), so streaming/library calls work immediately after a Google sign-in,
exactly like username/password login.

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

## 2026-09-24: `/muma/api/auth/login` answered by MuMa, not LMS

**Contract change (AGENTS.md rule 10).** `POST /muma/api/auth/login` used to be answered by LMS's
`MumaResource` with a flat `{id, username, display_name, is_admin, api_key}`, where `api_key` was
LMS's configured `api-key` for every user. It now answers with MuMa's own
`200 {status, api_key, access_token, refresh_token, user}` (the row in the API Contract table above),
`user` carrying `permissions`, `role_name` and `is_admin`. Errors are MuMa's: `401`, `403` disabled,
`429` rate limited.

- **nginx** (`services/music-management-server/nginx/reverse-proxy.conf`): `api/auth/login$` left the
  regex of LMS-owned routes, so the login goes straight to `music-manager:8000` like the rest of
  `/muma/api/`. `scripts/test/reverse-proxy-routing.sh` pins the route.
- **Rate limit**: `rate_limit.client_key` keys on the left-most `X-Forwarded-For` entry. The direct
  location therefore uses `set_real_ip_from` (10/8, 172.16/12, 192.168/16), `real_ip_header
  X-Forwarded-For` and `real_ip_recursive on`, and sends MuMa `X-Forwarded-For: $remote_addr` -- the
  right-most address not written by a private-network proxy -- instead of the whole chain, so a
  client cannot start a fresh bucket per guess by prefixing an address of its choice. The routing
  test sends forged chains and asserts what MuMa receives. The per-account bucket is unchanged.
- **LMS**: the local login handler is deleted. `/api/auth/login` joins `isPublicAuthPath`
  (`Authentication.cpp`), so a login that reaches LMS directly -- `lms.<domain>` and the test/dev
  stacks have no nginx in front -- is proxied to MuMa unauthenticated, like setup and Google, and
  gets the same answer. That hop carries no client address, so there MuMa counts per account only,
  as it already does for LMS's per-request password check. LMS's `api-key` stays: it is what MuMa
  presents when it calls LMS (`MUMA_SERVER_API_KEY`/`LMS_API_KEY` in `routers/users.py`).
- **Frontend**: `login.js`'s `startManagementSession` accepts only MuMa's shape (no `api_key` or no
  `user` object = no session, nothing stored). At startup `hydrateMumaUserFromApiKey` treats a key
  that verifies as `type: "system"` as a leftover of the old login and calls
  `endLeftoverSharedKeySession` (= `endRejectedSession`); `Management.svelte` does the same instead
  of setting `is_admin: true`. `isAdmin` therefore comes only from the Subsonic `adminRole` or the
  user's own `is_admin`/`role_name`. `mumaGate.js` moved the login from the proxy lane to the direct
  lane.
- **Consumers**: MuMa Mobile logs in against MuMa itself (`MumaAPIDefinition.login`,
  `MumaStoredCredentials`) and is unaffected. The contract tests log in through Subsonic and the
  BDD steps call MuMa's `/api/auth/login` directly; neither goes through the changed route.
- **Tests**: `src/libs/muma/test/Authentication.cpp` (`isPublicAuthPath`),
  `services/frontend/tests/unit/login.test.js`, `store.test.js`, `management.test.js`,
  `mumaGate.test.js`, and the routing script.
