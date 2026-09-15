# Car Mode Keeps Showing The Previous Track

# status: fixed — `MediaPlayerManager.publishPlaybackState` reports the window index, so the plugin's expectation can land; the tracker also gives up on an index that never arrives

# reported problem
The phone's car-mode screen (the web `CarModeView`, muma-mobile 7.0.0 debug builds) keeps showing
the track the trip started with after the native service has moved on to the next one. Reported
2026-09-15 from the car. Android Auto's own now-playing on the head unit was correct throughout,
and the notification too — only the WebView was behind.

# Possible reason
`CarModeView` draws `$currentTrack`, which on a native shell is moved only by what the Kotlin
plugin reports: `MumaPlayerPlugin.onPlayerState` runs every `RxBus.StateWithTrack` through
`TransportTracker.accept(trackId, index)` and emits `durationchange`/`command` to the web from
that. Since !779 the tracker *expects* the index the plugin itself asked `seekTo` for, and
swallows every state until the player reports exactly that index — the fix for the setQueue
feedback loop.

That expectation compared two different index spaces. `MediaPlayerManager.publishPlaybackState`
reported

```kotlin
index = if (isShufflePlayEnabled) getCurrentShuffleIndex() else currentMediaItemIndex,
```

— the play-order position under shuffle, kept for the deleted Kotlin queue screen that listed
the queue in play order — while `startAt(index)` and `expect(index)` work in window indices.
With shuffle on (in the service since !764) the reported index only matched by coincidence, the
expectation stayed pending, and every later state — including the real track changes — was
suppressed. The web never heard of them, so `currentTrack` froze on the first track of the trip.
Without shuffle the indices agree and the bug is invisible, which is why the emulator proof of
!779 passed.

Two smaller gaps sat behind it: `Player.svelte` only moved `currentTrack` on a `command` event,
never on a `durationchange` whose snapshot names a different `trackId`, and `CarModeView` read
only the playback status on mount, so a move that happened while the WebView was dead stayed
unseen even once events flowed again.

# solution
- `publishPlaybackState` reports `currentMediaItemIndex` in every mode; the shuffle-index helpers
  had no other reader and are gone.
- `TransportTracker` settles an expectation that cannot land: after three identical non-null
  track/index reports it adopts that state quietly (no synthesised next/previous), so a stuck
  expectation can never silence the plugin for the rest of the session. `TransportTrackerTest`
  covers the unreachable and the superseding expectation.
- `Player.svelte` reconciles `currentTrack` by `trackId` on `durationchange`, and
  `handleNativeCommand` no longer steps the queue by the command name when the snapshot already
  names the track, so the pair does not move twice. `CarModeView` adopts the plugin snapshot on
  mount and on `durationchange`.

Verified: `:app:compileDebugKotlin`, `TransportTrackerTest` (7 tests), ktlint and detekt green
locally; frontend vitest 1959 tests green.
