# Favorite Genres — Functional Design

> See [docs/designs/README.md](../README.md) for the overall process.

## Overview

Users can mark genres as "favorite" in the web player (`services/frontend`), which currently only
persists this choice to the browser's `localStorage` (`services/frontend/src/lib/store.js`'s
`favoriteGenres` store). This means the selection is lost when a user switches browser/device, clears
site data, or uses a different machine, and it never survives a fresh install.

This feature saves a logged-in user's favorite genres to their account in the `music-manager` database,
so the same favorites are loaded automatically every time that user opens the web interface, on any
device.

## User Stories

- As a logged-in web user, I want the genres I mark as favorite to be tied to my account, so that they
  show up automatically the next time I open the player, even on a different browser or device.
- As a logged-in web user, I want any favorite genre I add or remove to be saved immediately, so I never
  have to redo the selection.
- As a user who already had favorite genres saved locally (from before this feature existed), I want
  those to carry over to my account the first time I log in after the update, so I don't lose my existing
  selection.
- As a user browsing without an account (no `music-manager` login), I want favoriting genres to keep
  working locally exactly as before, so the feature doesn't regress for that case.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| Logged-in user opens the web UI on a device/browser that has no local favorites yet | Their previously-saved favorite genres (from the account) appear in the sidebar/dashboard, exactly as if they had set them on this device. |
| Logged-in user marks or unmarks a genre as favorite | The change is reflected immediately in the UI (as today) and is saved to their account; reloading the page or opening the app elsewhere shows the same result. |
| A user has local favorites saved (old behavior) and logs in for the first time after this feature ships, with no favorites yet saved to their account | Their existing local favorites are adopted as their account's favorites (one-time upload), so nothing appears to be lost. |
| A user has favorites saved to their account already, and also has different local favorites on this device | The account's saved favorites take precedence and replace the local ones on this device. |
| User is not logged in (anonymous/local-only use) | Favoriting genres continues to work exactly as before, stored only in this browser's `localStorage`. |
| User logs out | The favorite genres shown revert to this browser's local-only selection (do not leak the previous account's favorites to whoever uses the browser next). |

## Acceptance Criteria

1. A logged-in user who favorites a genre on device A sees that same genre favorited when opening the
   web UI, logged into the same account, on device B (or after clearing `localStorage` on device A).
2. Un-favoriting a genre while logged in also persists — it no longer appears as a favorite on another
   device/session for that account.
3. A user with pre-existing local-only favorites, logging in for the first time after this feature
   ships (account has no saved favorites yet), sees those same favorites preserved and now saved to
   their account.
4. Using the app while logged out (no account) behaves exactly as before this change — favorites are
   remembered locally in that browser only, with no network calls to load/save them.
5. Logging out and back in as a different account shows that other account's favorite genres, not the
   previous account's.

## Open Questions / Not Yet Decided

- None — this reuses the existing generic per-user app-settings mechanism (already used by MuMa Mobile
  for its own settings sync), so no new backend contract or data model decisions are needed. See
  [technical.md](technical.md).
