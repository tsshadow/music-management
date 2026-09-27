# Logout confirmation — Technical Design

Implements [functional.md](functional.md).

## Data Model

None.

## API Contract

None changed. The logout itself (`handleLogout` in `services/frontend/src/lib/ProfileButton.svelte`:
bounded native `signOut()`, bounded settings flush, `resetSessionState()`, `signedOut` marker,
reload -- bug report 106) is untouched; only what calls it changed.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| n/a | | | |

## Cross-App Impact

Frontend only. The app picks it up through the bundled web UI; no Kotlin change. Android Auto has
no logout entry point.

## Implementation

- The menu row calls `askLogout`, which closes the menu and sets `confirmingLogout`.
- The dialog reuses `Modal.svelte` (style guide: Components -> Modals / Confirmation dialog) with a
  new optional `widthClass` prop (`max-w-md` here; default stays `max-w-4xl`). `Modal` now also
  carries `role="dialog"`, `aria-modal` and `aria-label={title}`.
- Buttons follow the existing set-size confirmation in `TrackList.svelte`: outlined pill
  `common.cancel`, brand pill `common.logout`.
- The dialog is moved to `<body>` with the `portal` action (`src/lib/portal.js`). Both top bars are
  `backdrop-blur-md`, and a `backdrop-filter` ancestor becomes the containing block of a
  `position: fixed` child, so without the move the overlay would be clipped to the bar.
- `confirmLogout` guards with `loggingOut` and disables the button, so `handleLogout` runs once.
- i18n: `logout.confirmTitle`, `logout.confirmLost`, `logout.confirmKept` in `nl.json` / `en.json`;
  the dialects fall back to Dutch. `confirmKept` renders only when `platform.system.isNative`.

## Technical Acceptance Criteria

1. `tests/unit/profileButtonLogout.test.js`: the dialog appears and nothing is signed out before
   the answer; cancel leaves credentials, API key, queue and `signedOut` untouched and removes the
   dialog; confirm calls `platform.system.signOut` once even when tapped twice; the downloads line
   shows only on native. The existing logout tests go through the dialog.
2. No browser or e2e test clicked logout before this change, so none needed updating.

## Related Docs

- [docs/styleguide.md](../../styleguide.md) -- Session controls, Confirmation dialog.
- [docs/bug-reports/106-mobile-sign-out-and-google-sign-in.md](../../bug-reports/106-mobile-sign-out-and-google-sign-in.md) -- the sign-out path this dialog guards.
