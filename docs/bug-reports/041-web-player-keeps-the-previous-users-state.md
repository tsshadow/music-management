# The Web Player Keeps The Previous User's State, And Reads Errors As Data

# status: fixed

# reported problem
A review of `services/frontend` found six defects that share one pattern: state or an answer that
belongs to something else ends up on screen as if it were current.

- **Logging out left the previous user behind.** `ProfileButton.svelte`'s `handleLogout` cleared the
  credentials, the MuMa key, the refresh token, the session flag and `lms_active_view`. The queue,
  the current track, the player state, the sync mode, the page size, the equalizer and every
  account setting (home layout, display options, set-up progress) survived in localStorage, so the
  next person to sign in on that browser started inside the previous person's session.
- **Two setting changes in quick succession lost one of them; a failed read wiped the blob.**
  `saveFrontendSetting` read the whole `frontend` blob, set one key and wrote it back, with a
  separate 400 ms debounce per key. Two keys changed together meant two read-modify-writes in
  flight, and whichever wrote last removed the other's change. Worse, `loadFrontendSettings`
  answers `null` on any non-2xx, and the save then POSTed `{key: value}` as the entire blob — one
  401 or 500 on the read erased every other setting on the account, including the ones the
  Android app keeps there.
- **Error bodies were used as data.** `fetchMumaJson` never looked at `response.ok`, so a
  `{"detail": "..."}` came back as the answer. `listFeeds` then cached an empty feed list for the
  rest of the session; `Management.svelte` assigned error bodies into `users`, `config` and
  `accounts`. On the Subsonic side `subsonicJson` returned `status: "failed"` envelopes as data:
  error 40, a changed or expired password, rendered as an empty library instead of a login page.
- **Sets mode stayed green.** `AdvancedLibraryTab.svelte` and `Management.svelte` declared unlayered
  `:global(.text-brand)` / `:global(.bg-brand)` rules with `#1DB954`. Tailwind v4 puts its
  utilities in `@layer utilities`, and an unlayered rule beats a layered one regardless of
  specificity, so once either component had loaded, every brand-coloured element in the app was
  green, also under `:root.mode-sets`.
- **Artist and album pages could show the previous one.** `Dashboard.svelte` reused the same
  `ArtistView`/`AlbumView` instance when going from one artist straight to another, the loaders had
  no guard against an older answer arriving last, and `loadArtistInfo` only cleared the biography,
  similar artists and MusicBrainz id when the answer had no info block at all — a field artist B
  lacked kept artist A's value. The same late-answer race existed in the artist-curation queue and
  the advanced library tab.
- **The scrobble-import poll never stopped** when the tab was left: `ScrobbleTab.svelte` kept its
  3-second interval in a local.

# Possible reason
Each piece was written for the happy path of a single user and a single request: the logout list
was hand-kept and grew stale as stores were added, the settings helper was written for one key at
a time, the fetch helpers assumed a JSON body means success, and the detail views assumed an answer
belongs to the page that is still showing.

# solution
- `store.js` records every `persist()` registration, and `resetSessionState()` puts each one (except
  the MuMa server address, marked `device`) back to its declared value and drops its localStorage
  key, also resetting the non-persisted queue source and radio state and discarding pending
  account-setting writes. `handleLogout` flushes pending writes (bounded to 2 s) and then calls it.
  A store added later is covered without anyone editing the logout.
- Account-setting writes go through one queue: changes are collected per user, one debounced flush
  reads the blob once, merges everything pending and writes once. A failed read or write keeps the
  changes queued and retries after 10 s; a blob is never written after a failed read. The server
  contract is unchanged, so a per-key write on the server stays open work (`docs/open-work.md`) -- since done: bug report 116 added the per-key `PATCH`.
- `fetchMumaJson` throws a `MumaHttpError` (status and parsed body) on a non-2xx answer;
  `listFeeds` does not cache a failure or a body without a list; `Management.svelte` keeps each
  section at its default when its call fails; the error banner is reserved for every call
  failing, since one section a deployment cannot answer (the container list without a Docker
  socket) is not "the Management API is unreachable".
  `subsonicJson` throws a `SubsonicError` on any envelope that is not `status: "ok"`, and on error
  40 ends the session first (`endRejectedSession`), which puts the login page back up. Callers that
  page (the dashboard's tracks, albums and artists) now clear the list and stop paging on a
  failure instead of leaving the previous view's list standing.
- Both `:global` brand blocks are gone; `tests/unit/brandToken.test.js` fails if any `.svelte` file
  declares one again, and `docs/styleguide.md` states the rule. The setup wizard and release-notes
  modal use the token; the login page stays `#1DB954` on purpose, because it is shown before any
  mode applies.
- `Dashboard.svelte` renders `ArtistView` and `AlbumView` inside `{#key viewArgument(activeView)}`;
  both views clear every field at the start of a load, drop any answer whose request id is no
  longer current, and show an error state instead of a blank page. `ArtistCurationTab` and
  `AdvancedLibraryTab` got the same request-id guard.
- `ScrobbleTab` keeps its poll in a component variable, clears a running one before starting
  another, and clears it in `onDestroy`.
