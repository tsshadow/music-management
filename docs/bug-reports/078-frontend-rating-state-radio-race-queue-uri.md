# Web player: ratings out of sync between views, radio start race, 414 on long queues, localStorage churn

# status: fixed

# reported problem

Found in the September 2026 repository audit (item B10), four separate defects in
`services/frontend`:

1. **Ratings do not agree between views.** Rating a track in the track list left the player bar,
   Now Playing and car mode on the old stars (and the other way round) until the page reloaded.
   The rating write was implemented three times -- `TrackList.svelte` (`updateRating`),
   `Player.svelte` (`updateRating`, also behind Now Playing's and the details sheet's `onrate`) and
   `CarModeView.svelte` (`rate`) -- each with its own local "rating I last set" state.
2. **Radio can start twice.** Two quick taps on a channel, or picking a second channel while the
   first was still starting, ran both starts to completion: two `startRadio` calls on the native
   service, two radio controllers loading their streams into the same audio element, and a late
   failure of the first start tearing down the display of the second.
3. **Long queues fail with 414 URI Too Long.** "Save queue as playlist" (`App.svelte`,
   `createPlaylist`) and the jam push (`Player.svelte`, `savePlayQueue`) put one `songId=`/`id=`
   per track in the query string. A few hundred tracks is past what the proxies accept on a request
   line.
4. **`playerState` is written to localStorage about four times a second.** `persist()` in
   `store.js` wrote on every store change, and `Player.svelte` updates `progress` on every
   `timeupdate`.

# Possible reason

1. `tracks` reaches `TrackList` as a prop that is not always reactive in the parent, and the
   player's `track` is either the `currentTrack` store's object or one rebuilt from the radio
   timeline, so each view had added its own override map to make its stars repaint. Nothing shared
   those maps.
2. `startRadio` and `beginRadioDisplay` had no notion of "a newer start happened". The radio
   controller's `refresh()` checked its channel only before its fetch, so an answer that arrived
   after a switch was loaded anyway.
3. The Subsonic calls were written as GETs from the start; nothing measured the URL length.
4. `persist()` had a single mode -- write every change -- which suits settings but not a value
   that ticks with playback.

# solution

1. One rating module, `services/frontend/src/lib/ratings.js`: a `ratings` writable keyed by track id,
   `setRating(trackId, 1..5)`, `clearRating(trackId)` (Subsonic `rating=0`, relayed by LMS as
   `rating_removed`), and `tapStar(track, star)` for the rating rows (tap the lit star to clear).
   The write is optimistic, rolls back on failure with the existing `notify.error` message, and
   keeps a per-track generation so a late failure never undoes a newer tap. It also updates the
   `currentTrack` store when it holds the same track. `TrackList`, `Player` (and through it
   `NowPlaying` and `TrackDetailsSheet`) and `CarModeView` read `ratingOf($ratings, track)` and write
   through `tapStar`. 1 never means delete; clearing is only ever `clearRating`.
2. `services/frontend/src/lib/radioStartGuard.js`: every start takes a ticket; a repeat of the channel
   already starting is dropped, and only the newest ticket may touch state after its await.
   `toggleRadio`'s off path and `endRadioDisplay` invalidate outstanding tickets. The radio
   controller gained `retire()`, and `start()`/`refresh()` drop an answer for a channel they are no
   longer on, so a superseded controller never loads its stream.
3. `subsonicPost()` in `subsonic.js` sends the parameters as a form-encoded POST body (OpenSubsonic
   `formPost`, which LMS advertises and already honours for `getSongsByPath`), the credentials
   staying in the query string. `savePlayQueue` (jam push) and `createPlaylist`
   (`saveTracksAsPlaylist` in `queue.js`) use it. No LMS change was needed: its Wt request merges
   body and query parameters. Two contract tests in `tests/contracts/test_lms_subsonic_contract.py`
   pin that LMS accepts both calls with 400 ids in the body. Saving a playlist now also checks the
   Subsonic envelope instead of only the HTTP status.
4. `persist()` takes a `throttleMs` option (`throttledWriter` in `store.js`): a leading write, then
   one trailing write of the latest value per interval. `playerState` uses 5 s
   (`PLAYER_STATE_PERSIST_MS`). `flushPersistedStores()` writes anything pending and runs on pause,
   on `visibilitychange` to hidden and on `pagehide`; a logout cancels a pending write so it cannot
   restore the previous account's state.

Tests: `tests/unit/ratings.test.js` (optimistic update, rollback, stale-failure guard, a rating set
in the track list repainting car mode and the other way round), `radioStartGuard.test.js`,
`radioController.test.js` (retired controller loads nothing), two native `Player` tests in
`playerNativeMode.test.js` (a double tap starts once, the last channel picked wins),
`queuePost.test.js` and a `Player` test for the POST jam push, `playerStatePersist.test.js` (fake
timers).
