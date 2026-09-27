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
| Bundle downloaded and run | one chunk (no code splitting); blank until it runs | loaded from the APK, fast, but still blank |
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
| Genre / label / festival / podcast / year / lineup | `getSpotifyTracks`, pages one after another | the header shows, but the *previous* list stays on screen under the new name until the new one arrives |
| Search results page (`search:`) | three requests in parallel | the old results, or "No results" while the requests are still running |
| Starred, history, memories, daily mixes | one request each | header, then "Loading..." or a whole-body spinner |
| Search "more" modal | `search3` | a whole-body spinner |
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

## Open Questions / Not Yet Decided

- Whether the queue restore in the app should move *after* the first paint, with the mini player
  filling in afterwards. It is the biggest part of the app's start-up wait, but the restore must
  never disturb playback, which needs its own look. It stays as it is for now; issue filed.
- Which other pages follow first. Genre/label/festival lists, feeds, track versions and search each
  get a follow-up issue using the same building blocks. Feeds and track versions: done (#110,
  #111).
