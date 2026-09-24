# Authentication — Functional Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This is the
functional (user-observable) half of the login/access-request feature; the implementation contract is in
[technical.md](technical.md). Both are derived from the existing, code-verified
[docs/authentication.md](../../authentication.md), which remains the deepest-detail reference.

## Overview

Users can sign in to `music-manager` (and, through it, the LMS "Spotify UI") in one of two ways: with a
local username + password, or with "Sign in with Google". A person who signs in with a Google account that
isn't recognized yet doesn't get in automatically — they raise an access request that an administrator must
approve (either by creating them a new account, or by linking their Google identity to an account they
already have) before they can use the system. Administrators can also reverse an approval, reject a request
outright, or delete a user account directly.

## User Stories

- As a returning user, I want to log in with my existing username and password, so that I can access my
  library and playback the same way I always have.
- As a new user who only has a Google account, I want to sign in with Google, so that I don't need to
  remember a separate password for this system.
- As a new Google user who isn't recognized yet, I want to request access, so that an administrator can
  grant me an account without me having to ask them to create one manually first.
- As an administrator, I want to review and approve/reject pending access requests, so that only people I
  trust get access to the library.
- As an administrator, I want to link a Google sign-in to a user's *existing* account instead of creating a
  duplicate one, so that one person ends up with exactly one account regardless of how many ways they log
  in.
- As an administrator, I want to undo an approval I made by mistake, so that a wrongly-granted account (or a
  wrongly-linked identity) doesn't stay in place forever.
- As an administrator, I want to delete a user account directly, so that I can remove access for someone who
  no longer needs it, without that action silently failing or leaving orphaned data behind.

## Functional Flows

### Username + password login

| Situation | Observable outcome |
|---|---|
| The username doesn't exist | Login is refused with a generic "invalid username or password" message (the system does not reveal whether the username exists). |
| The account exists but has no password set (it's a Google-only account) | Same generic "invalid username or password" message, for the same privacy reason. |
| The account exists but is disabled | Login is refused with an "account disabled" message. |
| The account exists and the password is wrong | Same generic "invalid username or password" message. |
| The account exists and the password is correct | The user is signed in immediately. |

### Google Sign-In

| Situation | Observable outcome |
|---|---|
| The Google account has never been seen before, and no access request exists for it yet | The user is shown a screen to submit an access request instead of being signed in. |
| The Google account has never been seen before, but an access request already exists (pending, approved, or rejected) | The user sees the current status of their existing request instead of being asked to submit a new one. |
| The Google account was previously approved and linked to a user account, but that account has since been deleted | Sign-in is refused with a clear error. |
| The Google account is linked to an account that is disabled | Sign-in is refused with an "account disabled" message. |
| The Google account is linked to an enabled account | The user is signed in immediately, exactly as with a password login. |

### Approving, unapproving, and rejecting an access request

| Situation | Observable outcome |
|---|---|
| An administrator approves a pending request as a new account | A new, non-administrator account is created for the requester; the administrator may optionally set/override the display name shown for that account. |
| An administrator approves a pending request by linking it to an existing account | The requester can now also sign in with Google, using their existing account; no duplicate account is created; the administrator may still set/override the display name. |
| An administrator rejects a pending request | The request is marked rejected; no account is created or changed. |
| An administrator undoes ("unapproves") a request that had created a new account | That account is fully removed, and the request goes back to "pending" so it can be reviewed again. |
| An administrator undoes ("unapproves") a request that had linked an existing account | Only the Google sign-in link is removed; the pre-existing account is left completely untouched, and the request goes back to "pending". |

### Deleting a user directly

| Situation | Observable outcome |
|---|---|
| An administrator deletes a user account that is the last remaining administrator | The deletion is refused with a clear explanation, so the system can never end up with no administrator at all. |
| An administrator deletes any other user account | The account and everything tied to it (sign-in links, sessions, saved playlists, per-app settings, listening-history links) is removed; if the deletion fails for any reason, a clear error message is shown instead of a generic failure. |

## Acceptance Criteria

1. A user with a valid username and password can always sign in, regardless of whether they've also linked a
   Google account.
2. A user attempting username+password login never learns, from the error message alone, whether the
   username they typed exists in the system.
3. A disabled account cannot sign in via either method, and is told clearly that the account is disabled.
4. A first-time Google sign-in for an unrecognized account always results in an access-request flow, never
   in silent account creation or a silent rejection.
5. Submitting the same access request twice (e.g. by refreshing the page) never creates two separate pending
   requests for the same Google account.
6. An administrator can choose, at approval time, whether a request becomes a brand-new account or gets
   linked to one of the existing accounts, and can optionally set the display name either way.
7. Undoing an approval always restores the system to a state equivalent to "this request was never
   approved" — either the created account is gone, or the linked account is unaffected other than losing the
   Google sign-in link.
8. The system always has at least one administrator account; no action through the normal user-management
   screens can remove the last one.

## Open Questions / Not Yet Decided

- **Accounts with neither a password nor a linked Google identity.** Today, an account created without a
  password and never linked to Google can never actually sign in. Should account creation require at least
  one of the two, or should the admin UI simply warn when this happens?
- **Login attempt limiting.** Should repeated failed login/Google-verification attempts eventually be rate
  limited or locked out, and if so, per account, per IP, or both?
- **Self-service password reset.** Is a "forgot password" flow (e.g. via email) needed, or is admin-driven
  password reset (`users.update` permission) sufficient for the expected number of users?
- **Auto-generated username collisions.** Should a collision when auto-generating a username from a Google
  account (extremely unlikely, but currently a hard failure) be handled with a friendly retry/suffix instead?

## 2026-09-24: the web login hands each user their own key

**Decided by Teun.** Signing in to the web player with a username and password used to give every
user the same key: the music server (LMS) answered `/muma/api/auth/login` itself and returned its
own configured `api-key`. Where that value was also MuMa's system key, every web user held a key
MuMa treats as an always-allowed superuser, and the web app showed everyone who held it as an
administrator.

Now the web login is MuMa's own login, exactly as the phone app already used:

- Each user receives **their own** key, their own permissions and a refresh token. What the
  management screens show and allow follows that user's role, not a shared key.
- **Every web user signs in once more** after this ships. A browser that still holds the old shared
  key is recognised at startup (MuMa verifies it as a system key, not a user): the session ends and
  the login page comes back. From then on the key in that browser is the user's own.
- Nothing changes for the phone app (it already logged in with MuMa itself) or for Subsonic clients
  (they never used this key).

Acceptance: a non-admin user who signs in on the web never sees the management screens as an
administrator; an admin who signs in does, because their own account says so.
