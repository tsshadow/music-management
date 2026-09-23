# Authentication & User Model

> **Canonical acceptance criteria**: the functional and technical acceptance criteria for login are now
> maintained in [`docs/designs/authentication/functional.md`](designs/authentication/functional.md) and
> [`docs/designs/authentication/technical.md`](designs/authentication/technical.md), following the
> design-doc process in [`docs/designs/README.md`](designs/README.md). This document remains the deepest
> level of implementation detail those two files link back to; it is not deleted or superseded.

This document is the single source of truth for how login works in `music-manager`
(`services/music_manager/routers/users.py`, `routers/user_requests.py`, `rbac.py`). It exists so the
model and its edge cases don't have to be re-derived from the code every time.

## User model

A row in the `users` table always has:

- **`id`** (auto-increment) — the only field that is *always* guaranteed to exist and never chosen by the
  caller.
- **`username`** — required at the database level (`UNIQUE NOT NULL`), but the *caller* never has to pick
  one: for an account created through Google approval (see below) it is auto-generated from the email
  address (or, if there is no email, from the Google subject: `google-<subject_prefix>`). In that sense the
  username is "optional" from the end user's point of view — it always ends up populated, but never
  something a Google-only user is asked to type in.
- **`password_hash`** — optional. `NULL` for an account that has only ever logged in via Google; set for an
  account created via `/api/auth/setup` (first admin) or `/api/users` (local/Subsonic account).
- **`email`** — optional. Always set for a Google-approved account (it comes from the Google ID token
  claims); may be `NULL` for a purely local/Subsonic account that was never linked to Google.
- **`role_id`** → `roles.name` (`admin` or `user`) — every user has exactly one role, which is the *only*
  source of authorization (see `rbac.py`); the legacy `is_admin` boolean is still present as a read-only,
  derived convenience field (`role_name == 'admin'`), never written to directly and never checked for
  authorization.
- **`enabled`** — defaults to `TRUE`; a disabled account can't log in (`403`) with either method.

**Effective invariant**: a user account is only useful if it can actually be authenticated with, i.e. it
must have *at least one* of:
1. `password_hash` set (enables username+password login), **or**
2. a row in `user_identities` (`provider='google'`) linking it to a Google subject (enables Google login).

An account with neither (e.g. created directly via `POST /api/users` without a password and never linked to
Google) exists but is currently unreachable via `/api/auth/login` or `/api/auth/google` — this is flagged
under [Gaps / things to consider](#gaps--things-to-consider) below.

Separate, related tables:
- **`user_identities`** (`user_id`, `provider`, `provider_subject`, unique per `(provider, provider_subject)`)
  — the login-method-to-account mapping. A user can have zero, one, or (in principle) several identities
  (currently only `provider='google'` is implemented).
- **`user_requests`** — a pending/approved/rejected *access request* raised by an unknown Google identity;
  see the [approve/unapprove](#approving--unapproving-an-access-request) section below.
- **`user_refresh_tokens`** — long-lived tokens issued alongside the access token (`api_key`) so a client
  doesn't have to re-authenticate with Google/local credentials every time.
- **`audit_events`** — append-only log of `user_request.*` / `user.*` actions (who did what, to whom, when).

## Login flows

### 1. Username + password (`POST /api/auth/login`)

| Situation | Result |
|---|---|
| No user exists with that `username` | `401 Invalid username or password` (generic — does not reveal whether the username exists) |
| User exists but has no `password_hash` (Google-only account) | `401 Invalid username or password` (same generic message, for the same reason) |
| User exists, account `enabled = FALSE` | `403 Account disabled` |
| User exists, wrong password | `401 Invalid username or password` |
| User exists, correct password | `200` — issues/refreshes an `api_key` (access token) and a new `user_refresh_tokens` row (refresh token), updates `last_login_at` |

### 2. Google Sign-In (`POST /api/auth/google`)

| Situation | Result |
|---|---|
| The Google subject (`sub` claim) has **no** `user_identities` row, and no `user_requests` row exists for it either | `200 {"status": "unknown", "google": {...}}` — the frontend then shows an access-request screen |
| Same, but a `user_requests` row already exists (any status) | `200 {"status": "request_<status>", "request": {...}}` — e.g. `request_pending`, so the frontend can show "your request is pending" instead of asking again |
| The subject **is** linked (`user_identities` row exists), but the linked user no longer exists | `404 Linked user no longer exists` |
| The subject is linked, linked user `enabled = FALSE` | `403 Account disabled` |
| The subject is linked, linked user is enabled | `200` — issues/refreshes an `api_key` and refresh token, exactly like a password login |

Submitting an access request (`POST /api/auth/access-request`) is a distinct, explicit step from the above
(the frontend calls it once the user confirms they want to request access): it is idempotent per Google
subject — calling it again just returns the existing (pending/approved/rejected) request instead of creating
a duplicate.

## Approving / unapproving an access request

An admin (`user-requests.read`/`approve`/`reject`/`unapprove` permissions — granted to the `admin` role
only, **never** the default `user` role) reviews pending requests via `/api/user-requests`.

### Approve (`POST /api/user-requests/{id}/approve`)

Only allowed while `status = 'pending'`. Two modes, both of which move the request to `status = 'approved'`:

- **Create a new account** (default): a brand-new `user`-role account is created (**never** `admin`), with a
  `user_identities` row linking it to the Google subject. The account's `display_name` defaults to the
  Google profile's name, but the reviewer can override it by passing `display_name` in the request body
  ("optioneel koppel naam weergeven") — e.g. to fix a name Google reports oddly, or to match the naming
  convention already used for other accounts.
- **Link to an existing account** (`link_user_id` in the request body): used when the requester already has
  an account (e.g. a local/Subsonic login) and is now also requesting Google access for the *same* person.
  Only a `user_identities` row is added to the existing account; no new account is created. `display_name`
  can still be passed to update the existing account's display name.

The request row records which mode was used (`linked_existing`), which the unapprove flow below relies on.

### Unapprove (`POST /api/user-requests/{id}/unapprove`)

Only allowed while `status = 'approved'`. This is the fix for "ik unapprove een user -> verwijderen":

- If the approval had **created a new account** (`linked_existing = false`): that account is fully deleted,
  reusing the exact same cleanup helper as `DELETE /api/users/{id}` (dependent rows: identities, refresh
  tokens, dynamic playlists, per-app settings, ListenBrainz link).
- If the approval had **linked to an existing account** (`linked_existing = true`): only the `user_identities`
  row is removed; the pre-existing account itself is left completely untouched (it existed before the
  request and isn't the request's to delete).

Either way, the request goes back to `status = 'pending'` so it can be reviewed again (approved, rejected,
or linked differently) instead of being stuck in a dead-end "approved" state that can never be revisited.

### Reject (`POST /api/user-requests/{id}/reject`)

Only allowed while `status = 'pending'`. No account exists yet at this point, so this simply marks the
request `rejected` — there is nothing to delete.

## Deleting a user directly (`DELETE /api/users/{id}`)

Independent of the request flow above (e.g. for an account that was never created via a Google request at
all). Cleans up the same dependent rows as the unapprove flow, refuses to delete the **last remaining admin
account**, and returns a clear `Verwijderen mislukt: ...` message instead of a bare `500` on unexpected
failures.

## The LMS `/muma` bridge (`MumaResource`)

LMS answers a handful of `/muma` routes itself -- media libraries, Subsonic tokens
(`/muma/api/admin/...`), the artist image and native artist lookup, track refresh, and
`/muma/users/...` -- and proxies any other `/muma/api/...` call that reaches it to MuMa (nginx sends
most of those to MuMa directly). Its authentication, in
`services/music-management-server/src/libs/muma/Authentication.cpp`:

- A key (`X-API-Key`, else `?apiKey=`) counts only if it equals LMS's own `api-key` or MuMa
  confirms it via `GET /api/auth/verify`. MuMa's positive answers are cached for 60 s;
  `/muma/users/sync` clears the cache. When MuMa cannot be asked the answer is `503`, not `401`.
- Otherwise a Subsonic `u`/`p` pair is checked through the password service.
- The caller is whoever the verified credential names -- the password service's user, or the user in
  MuMa's verify answer. The `u` parameter never names the caller when a key was used.
- Media libraries and Subsonic tokens need a verified admin **user**; a system key (LMS's `api-key`
  or MuMa's) authenticates but is nobody. `/muma/users/sync` takes a system key or an admin.
  `/muma/users/{id}/settings/{app}` takes the user whose MuMa id is `id`, or an admin.
- The proxy forwards the caller's own verified key and nothing else; a `u`/`p` caller reaches MuMa
  without a key. The configured MuMa system key is used only for LMS's own calls on behalf of an
  already-verified caller (artist image, track refresh, settings).

Bug report [037](bug-reports/037-lms-any-key-is-admin.md) describes what this replaced: any
non-empty key was accepted and the caller was taken from `u`.

## Gaps / things to consider

Answering "mis ik hier nog dingen?" (things not covered above and not implemented in this pass):

- **An account with neither a password nor a Google identity is a dead end.** `POST /api/users` (used by
  the "add user" admin UI) can create a user without a password; unless a password is set afterwards
  (`POST /{id}/password`) or a Google identity is linked, that account can never actually log in. Consider
  either requiring one of the two at creation time, or surfacing a warning in the admin UI.
  **Not implemented in this change** (out of scope: touches the "create user" admin form, not the login
  flows themselves).
- **Rate limiting covers the password endpoints, not `/api/auth/google`.** `/api/auth/login`,
  `/api/auth/refresh` and `/api/auth/setup` refuse a caller that keeps being rejected
  (`services/music_manager/rate_limit.py`); repeated ID-token verification failures against
  `/api/auth/google` are still unlimited. Note that `/api/auth/login` is not only a login form: LMS
  calls it to validate the password on *every* Subsonic request, so anything counted there is counted
  per library page view, not per login.
- **No self-service password reset / email verification.** Password changes currently require either an
  admin (the admin role; any admin's password needs one too) or the user's own session plus their current
  password (`POST /{id}/password` with `current_password`); there is no
  "forgot password" email flow, and a Google-account's `email` is trusted as-is from the ID token without a
  separate verification step (Google already verifies it, so this is arguably fine, but worth noting).
- **Auto-generated usernames can theoretically collide** (`google-<subject_prefix>` is only the first 12
  chars of the subject) — extremely unlikely in practice, but the `INSERT` would fail with a duplicate-key
  `500` rather than a friendly retry/suffix. Not hardened in this change.
- **Merging duplicate accounts** (e.g. a Google request approved as a *new* account when the person already
  had a local account) is already solved separately by `POST /api/users/{id}/merge` — mentioned here only
  as a cross-reference, since it's the other half of "getting rid of a duplicate account".
