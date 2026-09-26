# Two quick taps on "next" left the app flickering between two tracks

# status: fixed

# reported problem

Teun, 2026-09-26, MuMa app 7.5.0 (web UI of server 0.75.0): tapping "next" twice very quickly makes
the player hang. It keeps flickering between the current and the next track and does not settle.
Not a regression of the last releases -- it has been possible for longer, and only a genuinely fast
double tap triggers it.

# Possible reason

On the phone the Svelte player (`services/frontend/src/lib/Player.svelte`) drives the native media3
service through `nativeQueue.js`. Before the fix, the on-screen next button did in native mode
exactly what it does in a browser: it computed `index + 1` from the UI's own `currentTrack` and set
`currentTrack` to that entry. The queue-sync effect then pushed the whole queue with that index
(`setQueue`), which the plugin applies as a queue replacement and reports back once as a
`durationchange` naming the settled track, *before* the `setQueue` call resolves (two bridge
messages, in that order).

Every service report is mirrored into `currentTrack` by `handleDurationChange` /
`handleNativeCommand`, and that write re-runs the same queue-sync effect. The only thing that kept
such a mirror from being sent back as a request was `push()`'s check that the engine snapshot
(`player.state().trackId`) already named the track -- read when the promise chain got round to the
push, not when the report arrived.

With two taps on a queue A, B, C, D (the second tap before the first move is reported):

1. Tap 1: `currentTrack` = B, push B (`setQueue(index 1)`) goes across.
2. Tap 2: `currentTrack` = C, push C is queued behind push B.
3. The service reports B. The UI (on C) mirrors it: `currentTrack` = B, push B' is queued behind
   push C.
4. `setQueue(1)` resolves; push C runs: `setQueue(2)`.
5. The service reports C. The UI mirrors it: `currentTrack` = C, push C' queued behind push B'.
6. `setQueue(2)` resolves; push B' runs. The snapshot now says C, not B, so the mirror guard fails
   and B' goes across as `setQueue(1)` -- the service is sent back to B.
7. The service reports B, the UI mirrors it and queues B''; push C' runs against a snapshot that
   says B, and sends the service to C. And so on.

There is always exactly one stale mirror queued behind the request in flight, pointing at the other
track, so the loop never runs dry. The vitest reproduction (`playerNativeDoubleNext.test.js`, with a
fake plugin that orders its reports and resolutions the way the real bridge does) ran into its
40-call guard before the fix. Two tracks picked from the list in quick succession hit the same loop
through the same path. On the native side each flip was a full queue replacement (clear, reload,
seek), so every cycle also restarted buffering and could send a fresh "now playing"; plays that short never
reached the 5-second listen threshold, so no duplicate listens were recorded.

# solution

Three changes, each closing a different part of the loop:

1. **Next and previous are intents on a native shell.** `playNext`/`playPrev` call
   `platform.player.next()`/`previous()` (the plugin's `seekToNext`/`seekToPrevious`, the same move
   the notification, a headset and Android Auto make) instead of computing an index. The service is
   the only side that knows where it is; media3 masks each call, so a second tap is relative to
   wherever the first got to and N taps move exactly N tracks. Shuffle, repeat and the 3-second
   "previous restarts the track" rule are the service's own. The UI follows the resulting
   `durationchange`/`command` reports like any other native move. A jam follower still sends its
   next/previous to the host, as before.
2. **A mirror is never sent back.** `nativeQueue.follow(trackId)` is called right before the UI
   writes a track the service reported; the sync that write triggers is marked as a mirror at call
   time and only updates `pushedIndex`, however late the chain reaches it.
3. **Stale reports are dropped.** While a move this side requested is still in flight
   (`nativeQueue.isStale`), a report naming any other track is the service passing through an older
   request and is ignored by `handleDurationChange` and `handleNativeCommand`. Queue edits that keep
   the current track, and the boot sync, are not moves, so a genuine advance during their round
   trip still reaches the UI; once every requested move has finished, every report is authoritative
   again.

Tests: `services/frontend/tests/unit/playerNativeDoubleNext.test.js` (two taps, N taps, previous,
two quick list picks, two quick moves from outside the app -- all settle, none pushes a queue back),
`nativeQueue.test.js` (mirror and stale-report rules) and `ScrobbleLedgerTest` (a burst of skips
records only what was actually played, once each).
