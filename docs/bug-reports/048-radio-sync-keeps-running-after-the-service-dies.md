# Radio Sync Keeps Running After The Playback Service Dies

# status: fixed — the service shuts down once and cancels what it started; resumption, saving, plugin calls, radio start, MuMa login, downloads and the intent receiver fixed alongside

# reported problem
Found in a review of the Android app's service lifecycle (2026-09-24), not reported by a user. The
headline: once the playback service is destroyed, the radio sync loop keeps running. It calls the
MuMa API every 2 to 10 seconds for as long as the process lives, and calls into a player that has
already been released. Everything below was found in the same review; the first eight were
confirmed by reading the code, the radio start (item 8) by tracing it.

# Possible reason
1. **Nothing cancelled the service's coroutines.** `MediaLibrarySessionCallback` created
   `serviceJob` and `mainScope` and never cancelled either. `RadioPlaybackController`'s loop
   (`start`, a `while (isActive)` with a 2 s tick, a 10 s refresh and a 5 min clock measure) runs on
   `serviceScope`, so it outlived the service. `PlaybackService`'s own scope, used for download
   prefetching, was never cancelled either.
2. **The service could be destroyed twice.** The Rx shutdown command called `onDestroy()` by hand.
   The system then called it again after `stopSelf()`, so `player.release()`,
   `mediaLibrarySession.release()` and `super.onDestroy()` ran twice.
3. **Swiping the app away always stopped the music.** `onTaskRemoved` released the player and the
   session unconditionally, including while music was playing.
4. **Playback resumption could hang for good.** `onPlaybackResumption` returned a `SettableFuture`
   that was only completed when a saved state was read. With nothing saved, or when
   `deserializeNow` threw, the future stayed pending, and Media3 waits on it before acting on a
   Bluetooth play button or the system's resume card.
5. **The equalizer leaked.** Every local player created an `EqualizerController`, and so a native
   `Equalizer`. Nothing released it on a backend switch or on shutdown. `MumaPlayerPlugin.setEqualizer`
   read whatever `EqualizerController.get()` held, which could be an instance whose player was gone.
6. **The saved playback state could be one change behind.** `PlaybackStateSerializer.serializeAsync`
   returned without doing anything when a write was already in flight, so every update during a
   write was dropped, including the last one before the app died. The `isDeserializing` guard was
   never set to true, so it guarded nothing.
7. **Plugin work could crash the app and leave the web waiting.** `MumaStoragePlugin`,
   `MumaSystemPlugin`, `MumaPlayerPlugin` and `MumaSpeechPlugin` launched on a bare
   `CoroutineScope(Dispatchers.IO)`: no `SupervisorJob`, no exception handler, and three of the four
   never cancelled. An exception in a launched block crashed the process, and the JavaScript promise
   waiting on that call never settled.
8. **A radio channel could not start on the local player.** Radio items carry a finished,
   transcoded stream URL (`getTranscodedStreamUrl`). Every item the local player loads goes
   `CachedDataSource` → `ResolvingDataSource`. `CachedDataSource.open` finds no cached file for a URL
   and forwards it, and the resolver then split every URI that was not a news item on `|` and read
   `components[1].toInt()`. A URL has no `|`, so the result was an `IndexOutOfBoundsException` and
   the load failed.
9. **Every MuMa call logged in with the password first.** `RESTMusicService.ensureMumaLogin` only
   trusted `activeServer.apiKey`. That field is always null for the static servers, because
   `ActiveServerProvider.getActiveServer()` copies the entry from `StaticServers`. The key a login
   stores goes to `Settings.mumaApiKey`, and this code never read it. So every settings save, tile
   call and crash-report upload sent `POST /api/auth/login` first, which feeds the login rate limit.
10. **Downloads ran as a media-playback foreground service.** The manifest declared
    `foregroundServiceType="mediaPlayback"` for `DownloadService`, but Android 14 and later expect
    `dataSync`, with its own permission, for this kind of work. When Android refused a background
    start, the only trace was one log line, and the start future stayed pending. Every later
    download request then waited behind a start that never happened, until the process was
    restarted.
11. **Any app could control playback.** `UltrasonicIntentReceiver` was exported without a
    permission, so any installed app could send it play, pause, next or stop.

# solution
1. `PlaybackService` has one idempotent `shutdown()`, used by `onDestroy`, the Rx shutdown command
   and a swipe-away with nothing playing. It calls `MediaLibrarySessionCallback.release()` first,
   which releases the radio controller and cancels `serviceJob` and `mainScope` (now with a
   `SupervisorJob`). It then releases the equalizer, player and session, and cancels the service's
   own scope. `RadioPlaybackController.release()` sets `isReleased`. From then on `start` refuses,
   and neither `tick`, `loadEntryAt` nor `stop` touches the player.
2. The Rx shutdown command calls `shutdown()`, not `onDestroy()`.
3. `onTaskRemoved` stops the service only when `!playWhenReady || mediaItemCount == 0`
   (`PlaybackServiceRules.shouldStopOnTaskRemoved`).
4. `PlaybackResumption.resume` always completes the future. It fails with
   `NothingToResumeException` when nothing is saved (as Media3's own default does), with the read
   error when loading throws, and with the cancellation when the service is already gone.
5. `EqualizerController.release(controller)` releases the native effect, cancels the controller's
   scope and marks it `isReleased`. `PlaybackService` calls it on a backend switch and on shutdown,
   and `setEqualizer` ignores a released controller.
6. Writes are coalesced. An update during a write replaces the pending state, and the newest one is
   written as soon as the current write ends. The track list is copied on the caller's thread, and a
   failed write no longer stops later ones. `isDeserializing` is now set with `compareAndSet`, so a
   second restore during the first is refused, and a restore can no longer append the queue twice.
7. `PluginCallScope` gives each plugin `SupervisorJob() + Dispatchers.IO + handler`, and every
   plugin cancels it in `handleOnDestroy`. `runCall(call) { answer -> }` settles each call exactly
   once through `CallAnswer`. An exception rejects the call, cancellation rejects it as cancelled,
   and a second answer is dropped.
8. `PlaybackServiceRules.streamTargetOf` passes an `http`/`https` URI through unchanged. Only the
   `id|bitrate|path` shape is resolved, and a missing bitrate falls back to 0.
9. `MumaStoredCredentials.resolve` takes the server entry's key and id when it has them, and
   otherwise `Settings.mumaApiKey`/`Settings.mumaUserId`. A login happens only when no key is
   stored, or once when the server answers 401 (`retryOnceWhenUnauthorized`), and the call is then
   repeated.
10. `DownloadService` is a `dataSync` foreground service and declares
    `FOREGROUND_SERVICE_DATA_SYNC`. `onTimeout` stops it when Android 15's daily six hours run out.
    A refused start is logged at WARN with the exception and its message, and the start future is
    failed and forgotten, so the next request tries again.
11. `UltrasonicIntentReceiver` is no longer exported. Its only senders are the app itself: the
    widget's `PendingIntent`s, which name the component explicitly, and `BluetoothIntentReceiver`'s
    package-scoped broadcasts.

Pinned by `PlaybackServiceRulesTest`, `PlaybackResumptionTest`, `PlaybackStateSerializerTest`,
`PluginCallScopeTest`, `MumaStoredCredentialsTest` and `RadioPlaybackControllerReleaseTest`.

**What no test covers.** Robolectric draws nothing and nothing starts the release build. Whether
music survives a swipe, whether a Bluetooth play resumes, and whether a channel actually plays on a
phone are unverified until someone tries them on a device, which is listed in `docs/open-work.md`.
Item 8 was reached by reading the code, not by watching it fail on a phone.
