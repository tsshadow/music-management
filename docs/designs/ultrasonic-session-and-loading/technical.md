# Ultrasonic session control & home screen loading — Technical Design

Implements [`functional.md`](functional.md). Everything here lives in `services/ultrasonic`; no
backend, frontend or LMS change is involved.

## Data Model

No database change. The session lives in existing settings:

| Setting | Role in this design |
|---|---|
| `Settings.staticUserName` | Kept on logout, so the login screen can prefill it. Not a credential. |
| `Settings.staticPassword` | Cleared on logout. Blank is what `NavigationActivity.onCreate` already reads as "not logged in". |
| `Settings.mumaApiKey` / `Settings.mumaUserId` | Cleared on logout; both authenticate against MuMa. |
| `SecureSettings` (encrypted prefs) | Cleared on logout; holds the MuMa access/refresh tokens. |

## API Contract

No endpoint is added or changed. One existing server behavior is newly acted on: the Subsonic error
code `40` (`SubsonicError.WrongUsernameOrPassword`), which the server already returns and which the
client previously only turned into a message.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| *(unchanged)* any Subsonic call | unchanged | unchanged | error `40` now additionally ends the session; `50` (not authorized), `70` (not found) and all others behave exactly as before |

## Cross-App Impact

None. The behavior is entirely client-side and consumes an already-specified Subsonic error code.

## Home screen loading

`HomeViewModel` published `List<HomeSection?>` in a single shot after every provider had finished,
inside one `withContext(Dispatchers.IO)`. Two consequences: nothing was drawn until the slowest
section was done, and the sections ran one after another.

- `HomeSectionState` (new) is `Loading | Empty | Content(HomeSection)`, one per slot.
- `HomeViewModel.sections` becomes `StateFlow<List<HomeSectionState>>`. `load()` launches one
  coroutine per provider and publishes each slot as it completes, so slots fill in independently.
  A provider that throws yields `Empty` rather than cancelling its siblings.
- A reload keeps existing state per slot (`getOrElse { Loading }`), so returning to the home screen
  never flashes skeletons over content that is already there.
- `LibraryActivityProvider.load()` runs its three sources (artists, albums, labels/festivals)
  concurrently with `async` inside a `coroutineScope`, turning three sequential round trips into
  one. This is the actual latency fix; the skeletons cover what remains.
- `HomeViewModel` gained two test-only constructor parameters (`ioDispatcher`, `providers`), both
  defaulted, so the state machine is unit-testable without Android or a server.

`MainFragment` renders a state per slot: `Loading` shows the skeleton and hides the title and the
recycler, `Content` does the reverse, `Empty` hides the whole section. The skeleton layout
(`home_skeleton_grid` / `home_skeleton_carousel`) is inflated once per slot into
`section_skeleton_cards`, chosen by the slot's `CardStyle`, and its sizes mirror the real card
layouts so content lands where the placeholder was. The pulse is `R.anim.skeleton_pulse` (an alpha
animation); no shimmer library is introduced.

## Logout

`NavigationActivity.logOut(messageRes)`:

1. `mediaPlayerManager.clear()` — what is playing was streamed with credentials that are about to
   be dropped.
2. Clears `Settings.staticPassword`, `Settings.mumaApiKey`, `Settings.mumaUserId` and
   `SecureSettings`.
3. `activeServerProvider.invalidateCache()` + `MusicServiceFactory.resetMusicService()` so no
   cached client keeps using the old credentials.
4. Sets `UApp.instance!!.setupDialogDisplayed = false` and calls `showWelcomeDialog(messageRes)` —
   that flag is the once-per-app-start guard on the login dialog, and a fresh logout is exactly when
   it must show again.

Entry point: a `menu_logout` item in `search_view_menu.xml` (the toolbar overflow), handled in
`searchMenuProvider.onMenuItemSelected` next to the existing `menu_exit`, behind a confirmation
dialog. `showWelcomeDialog` takes an optional `@StringRes` message shown in its error slot, and
prefills the kept username.

Signing back in needs its own signal: `ActiveServerProvider.setActiveServerById` returns early when
the id is unchanged, so logging in again on the same server fires no `activeServerChanged` and the
home screen would keep whatever it loaded (or failed to load) while logged out. Both success paths
of the welcome dialog therefore emit `RxBus.loginSucceededPublisher`, which `MainFragment` reloads
on.

## Rejected credentials

The API module cannot see the app module, and every screen swallows its own errors, so the
detection point is the one place all API results pass through: `throwOnFailure()` in
`core/subsonic-api`.

- `AuthenticationFailureNotifier` (new, in `core/subsonic-api`) holds a nullable listener and is
  called from both `throwOnFailure()` overloads. It forwards **only**
  `SubsonicError.WrongUsernameOrPassword`.
- `UApp.onCreate` registers the listener and republishes it on
  `RxBus.authenticationFailurePublisher`. Registering in the Application (not an Activity) means a
  background call is noticed too.
- `RxBus.authenticationFailureObservable` throttles to one event per 5 seconds, because a burst of
  parallel requests all fail at once and the session only needs to be ended once.
- `NavigationActivity` subscribes and calls `logOut(R.string.welcome_session_expired)`, guarded by
  "not offline" and "a password is actually set" so a logged-out or offline app cannot loop.

## Technical Acceptance Criteria

1. `AuthenticationFailureNotifierTest` proves error `40` reports through both `throwOnFailure()`
   overloads, and that errors `50` and `70` do not.
2. `HomeViewModelTest` proves: all slots start `Loading`; a finished slot publishes while others
   still load; a `null` section becomes `Empty`; a throwing provider becomes `Empty` without
   affecting its neighbour; a reload keeps existing content.
3. `HomeSectionProviderTest` (existing) still passes with the concurrent `load()`, including the
   "a failing source does not sink the whole section" case.
4. `./scripts/test/android-unit.sh` passes.

## Related Docs

- [docs/styleguide.md](../../styleguide.md) — skeleton loading pattern and the logout entry.
- [docs/authentication.md](../../authentication.md) — how the app authenticates in the first place.
