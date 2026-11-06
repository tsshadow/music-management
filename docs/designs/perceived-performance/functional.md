# Perceived performance — Functional Design

Issue #107. Requested by Teun on 2026-09-27.

## Overview

The app is often not slow, but it *looks* slow, for two reasons:

1. **Start-up shows an empty screen.** Until the bundle has run, and in the MuMa Mobile app until
   the server, the session and the playback queue are restored, nothing tells the listener that
   anything is happening.
2. **Opening an artist or album hides everything that is already known.** The list the listener
   tapped already has the artist's name and picture, or the album's title, cover and artist. The page
   still showed a bare "Loading..." until the *whole* artist had loaded, and only then asked for the
   artist's tracks.

The request was to fix these two, and also to look for the general pattern behind them and fix that.
The measurements below show that it is general: nearly every page that opens a thing (artist,
album, track versions, feed) waits for the network before it draws any of it.

## Measurement (2026-09-27, code paths on develop `9a817cc50`)

**Start-up**

| Phase | Browser | MuMa Mobile shell |
|---|---|---|
| `index.html` parsed | empty `<div id="app">`, a black page | same |
| Bundle downloaded and run | one chunk (no code splitting until #114); blank until it runs | loaded from the APK, fast, but still blank |
| Before `mount` | nothing | `bootstrapShell` (`nativeSession.js`): server URL (bridge), sign-in (**network**: ping + MuMa login, skipped when the stored session matches), queue restore (**network**: one `getSong` per queued track, up to 200, in parallel) |
| After `mount` | shell or login page appears at once; home shelves fill in | same |

So the empty screen in the app is the queue restore and the sign-in. Both happen *before* anything
is mounted, with nothing on screen.

**Pages that wait for data before drawing**

| Page | Requests | What shows while waiting |
|---|---|---|
| Artist | `getArtist`, and only after it finishes `getSpotifyTracks`, `getArtistInfo2` and the MuMa genre rules | the whole page is "Loading..." until `getArtist` finishes; the tracks come a full round trip later |
| Album | `getAlbum`, then `getAlbumInfo2` | the whole page is "Loading..." |
| Track versions (`song:`) | `getSpotifyTracks?workId=`, pages one after another, up to 500 tracks | the whole page is "Loading..." |
| Feed / release radar / daily mix | `GET /api/feeds/{slug}`, then song chunks one after another | header, then "Loading..." |
| Genre / label / festival / podcast / year / lineup | `getSpotifyTracks`, pages one after another | the header shows, but the *previous* list stays on screen under the new name until the new one arrives. **Done (#109):** skeleton rows under the new name, cached per query, prefetched on press |
| Search results page (`search:`) | three requests in parallel | the old results, or "No results" while the requests are still running. **Done (#112):** a skeleton, error and retry per section, "Zoeken…" until all three answered |
| Search dropdown (top bar) | `search3`, after a 300 ms debounce | "No results" during the debounce, then "Loading..." in place of the previous results. **Done (#112):** "Zoeken…" from the first keystroke, previous results dimmed |
| Starred, history, memories | one request each | header, then "Loading..." or a whole-body spinner. **Done (#112):** skeleton sections, and an error with a retry for starred and history |
| Daily mixes | one request | header, then a whole-body loader. **Done (#110):** card-shaped skeletons in the grid |
| Search "more" modal | `search3` | a whole-body spinner. **Done (#112):** skeleton rows or tiles, error with a retry |
| Playlist | `getPlaylist` | header from the list that was tapped, and an empty list with no loading sign |
| Albums / artists / playlists grids | one request each | no loading state: empty or stale grid |

The playlist page already does half of what this design proposes: its header comes from what was
tapped.

## User Stories

- As a listener opening the app, I want to see that it is connecting and loading, so that I know it
  is not stuck.
- As a listener whose server is unreachable, I want to be told so and offered a retry, not a black
  screen.
- As a listener tapping an artist, I want the artist's page (name and picture) at once, with the
  tracks filling in after, so the app feels instant.
- As a listener going back to a page I just saw, I want it immediately, with any changes appearing
  quietly.
- As a listener on a slow connection, I want the parts of a page that are ready to show even while
  one part is still loading or has failed.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| App or browser tab opens | Straight away: a boot screen with the MuMa mark, a status line and a progress bar on the app's black background. |
| App: restoring the server and session | Status "Verbinden…", then "Inloggen…". |
| App: restoring the queue | Status "Wachtrij herstellen…", with a bar that fills as tracks come back. |
| A stage takes more than 8 s | A second line: "Dit duurt langer dan normaal". |
| Nothing has mounted after 20 s | A "Opnieuw proberen" button that reloads the page. |
| Bundle mounted | The boot screen fades out and the login page or the app appears. |
| Tapping an artist anywhere its name is shown | The artist page opens at once with that name and picture, and the play/shuffle/favourite buttons visible. Grey placeholder rows (skeletons) stand where the tracks and albums will go. Each section fills in as its data arrives. |
| Tapping an album | The album page opens at once with its title, cover and artist, with skeleton track rows. |
| Opening an artist/album by URL (refresh, shared link) | The same page layout, with a skeleton where the name and picture go, until the data arrives. |
| Going back to an artist/album seen in the last few minutes | The page shows the previous data immediately and refreshes it in the background. |
| One section fails (e.g. similar artists) | Only that section shows "Kon niet laden" with a retry. The rest of the page stays. |
| The artist itself cannot be found | The header says the page could not be loaded. |
| Pressing on a link (finger down, mouse down) | The page's main request starts before the finger lifts. No request is made just for hovering or scrolling past. |
| Tapping play before the tracks have arrived | The button shows a small spinner (throbber) and playback starts as soon as the tracks arrive. |
| Tapping a daily-mix card or the release radar (issue #110) | The feed page opens at once with the card's title and subtitle (the radar and the classic daily mix use their fixed copy). Skeleton rows stand where the tracks go. The tracks appear as each batch comes back from the server, always in the mix's own order. |
| Opening a feed by URL with nothing known | A skeleton title bar until the server names the feed. |
| Part of a feed fails to load | The tracks that did load stay; under them one line "Kon dit deel niet laden" with "Opnieuw", which asks for only the missing part. |
| The feed itself fails to load | The header stays; the body says it could not load, with "Opnieuw". |
| Tapping "Versies" on a track (issue #111) | The song page opens at once with the track's title, artist and cover. The versions appear page by page as they arrive, with skeleton rows under them while more are coming. |
| The track details sheet | The header, chips and file section are there at once; the tags section shows placeholder rows while MuMa is asked, and "Opnieuw" if it could not be reached. |
| A daily-mix card on a phone or tablet (issue #99) | The play button is always visible, 48px. With a mouse it appears on hover, as before. |
| Opening a genre, label, festival, podcast, year or lineup (#109) | Its name is the heading at once. Skeleton rows stand where the tracks go; the previous list is never shown under the new name. One seen in the last five minutes shows at once and refreshes quietly. |
| Changing a filter or sort on that list | The rows stay, dimmed, with a throbber next to the heading, until the new answer replaces them. |
| Pressing a genre/label/podcast/festival/year/lineup card | That list's first page starts loading before the finger lifts. |
| The list fails to load | "Kon dit deel niet laden" with "Opnieuw", instead of "Geen nummers gevonden". |
| Opening the search results page (#112) | "Zoeken…" next to the heading, skeleton rows for tracks and skeleton tiles for artists and albums. Each section fills in, or fails with its own retry, on its own. "Geen resultaten gevonden" only once all three have answered empty. |
| Typing in the search box (#112) | "Zoeken…" from the first keystroke. With nothing shown yet, skeleton rows; with results for the previous text, those stay dimmed. "Geen resultaten gevonden" only for an answer; a failed search offers "Opnieuw". |
| Opening the app on a page off the first screen by URL, e.g. Management or settings (#114) | The boot screen stays up until that page's code has loaded, then the app appears with the page. |
| Opening a settings tab for the first time (#119) | The tab's own shape in skeleton blocks for the moment its code takes to load, then the tab; the next tab in the list is fetched in the background, so switching to it rarely waits. |
| Tapping the mini player before Now Playing's code is in (#119) | Now Playing slides up at once with the cover, title, artist and a working play/pause; the rating, progress bar and other buttons fill in a moment later without anything moving. |
| Navigating to a page off the first screen for the first time (#114) | Skeleton rows for the moment its code takes to load, then the page. A second visit is instant. A page whose code could not load says so, with "Opnieuw". |
| Opening History, Starred or Memories (#112) | Header at once, skeleton rows or tiles where the content goes. History and Starred show an error with a retry when loading fails, instead of "nothing here yet". |

## Acceptance Criteria

1. From the first frame, a cold start shows the boot screen, never a blank page, in both the
   browser and the app.
2. In the app the status line walks through the stages. The queue stage has a filling bar.
3. After 20 s without the app appearing, a retry button is offered.
4. Tapping an artist in a track list, search results, the artists grid, starred or similar artists
   shows the artist's name in under ~100 ms on phone and tablet, while the tracks are still loading.
5. Tapping an album shows its title and cover in the same way.
6. The artist's tracks request starts at the same time as the artist request, not after it.
7. Revisiting an artist or album within 5 minutes shows it without a loading state.
8. A failing section shows its own error and retry. It never blanks the page.
9. Loading placeholders follow the style guide (Loading States).
10. A feed page shows its title (from the card, or fixed copy) and skeleton rows before MuMa has
    answered, and the first batch of tracks before the second one has (issue #110).
11. A feed's "N niet gevonden op de server" note, "Meer laden" and the queue continuation work as
    before (bug report 122, !1084, !1087).
12. The song page shows the tapped track's title, artist and cover before the versions have
    arrived, and the first page of versions before the last (issue #111).
13. A daily-mix card's play button is visible without hover on a touchscreen (issue #99).
14. The code the first screen waits for is well under half of the single 1.29 MB bundle it used to
    be; Management, settings, statistics and the other pages off the first screen load when opened,
    and still render when opened by URL, by navigation, in a browser served by LMS and inside the
    app (issue #114).
15. A track list (songs, sets, a genre, label, podcast, festival, year, lineup, search) shows its
    first 50 rows in the time a 50-row answer takes, whatever the listener's page size; the rest of
    the page follows behind them without moving what is on screen, versions folded across both. A
    revisit within 5 minutes shows the whole page at once. Leaving a list -- for another list or
    another page -- stops its request.

## Decisions

- **Prefetch on press only.** Prefetching on hover or while items scroll into view was rejected.
  A grid of 60 artists would fire 60 `getArtist` calls, and LMS serves the player and every other
  client from the same small thread pool (memory: LMS thread pool starvation). Pressing a link
  starts one request, which the page then reuses, gaining the 50-150 ms between finger-down and
  finger-up.
- **The cache lives in memory and is lost on reload.** Nothing is written to storage. Stale data
  survives at most one session and at most 5 minutes before a background refresh replaces it.
- **The name shown from a seed is replaced by the server's.** When a link's name turns out to be
  wrong (e.g. a track credited "A, B" whose link names A), the page corrects itself when the data
  arrives. It never keeps the guess.

- **Code splitting by page, not by component (#114).** The pages behind a tap -- Management and each
  of its tabs, settings, statistics, the edit pages, the setup tour, the car screen -- load when
  opened. Home, the track lists and the player stay in the first file: they are what a start
  shows. The pages one tap away (artist, album, feeds, the filter bar) followed in #118, each with
  a seeded stand-in so the heading still appears within 100 ms of the tap. Settings loads one tab
  at a time, and Now Playing is its own file too (#119): the mini player stays in the first file,
  and opening Now Playing shows the same screen at once from what the mini player knows, while
  its file is fetched -- in practice it already was, on idle or the moment a finger touched the
  mini player.

- **A small first page, whatever the page size.** `getSpotifyTracks` scales with `count`: on
  production a 200-row list took 1.3 s idle and 12-17 s while LMS scanned. The listener's page size
  (25-500) still decides how many rows the page holds and how many "Meer laden" adds; only the
  first request is capped at 50, and the rest is fetched behind the rows already shown.

## Open Questions / Not Yet Decided

- ~~Whether the queue restore in the app should move *after* the first paint, with the mini player
  filling in afterwards.~~ Decided and built in issue #113: see
  [deferred-queue-restore](../deferred-queue-restore/functional.md).
- Which other pages follow first. All the follow-ups are done: feeds and track versions (#110,
  #111), genre/label/festival lists and search (#109, #112).
