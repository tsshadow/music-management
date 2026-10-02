# Deferred queue restore — Technical Design

Implements [functional.md](functional.md) (issue #113).

## Data Model

None. No table, column, endpoint or plugin method changes.

## API Contract

No endpoint changes. The restore still calls `GET /rest/getSong?id=…` once per queued id (at most
`MAX_REHYDRATED_TRACKS` = 200), in parallel, through `subsonicJson` (so an offline start answers
from the downloaded library). There is no batch alternative: LMS `getSongs` filters by `clusters`,
`artistId`, `workId`, `form`, `year` and duration, not by track id.

## Moving parts

- **`main.js`** calls `bootstrapShell(..., { decide, deferQueue: true })` and mounts as soon as it
  resolves, i.e. after the server URLs and the session.
- **`nativeSession.js` / `bootstrapShell`**: with `deferQueue` and a session, it calls
  `beginQueueRestore()` *before* returning (so the first frame already sees `restoring`), starts
  `restoreQueue(...)` without awaiting it, and returns `restored: 0` plus `queueRestored`, a promise
  of the final count. The diagnostics trail gets `shell:boot` (`deferred: true`) at once and
  `shell:queueRestore` (`restored`, `cancelled`) when it ends. Without `deferQueue` the old order
  (restore, then resolve; boot stage `restoringQueue` with counts) is unchanged.
- **`queueRestore.js`** (new) owns the window between mount and restore:
  - `queueRestore` store: `{status: idle|restoring|restored|cancelled, done, total}`.
  - `beginQueueRestore()` keeps the `localStorage` queue as `ticket.leftover`, empties `playlist`
    and `currentTrack`, and subscribes to `currentTrack`. A non-null write that is not the
    ticket's own (`ticket.write(fn)` sets a flag around `fn`) is the listener starting a track:
    status becomes `cancelled` and the ticket stops being current, so every later `write` returns
    false and is dropped.
  - `withQueuedMeanwhile(tracks)` appends what `playlist` gained during the restore ("add to queue"
    edits `playlist` without a track starting, so it does not cancel).
- **`rehydrateQueue` / `rehydrateOfflineQueue`** take an optional ticket. With one they write
  through `ticket.write`, bail out after the lookups when the ticket is no longer current, re-read
  the engine snapshot (`platform.player.state()`, kept current by the plugin's events) so a track
  change during the lookups is followed, and put `ticket.leftover` back when the service holds no
  queue at all. `reconcileQueue` (offline stash) takes a `write` hook for the same reason.
- **`Player.svelte`** queue sync effect: returns before pushing anything while
  `$queueRestore.status === 'restoring'` and without flipping `nativeQueueSynced`, so the first sync
  after the restore is still the boot sync (`autoplay: false`, adopting). The one exception: when
  the status is `cancelled`, the first sync is the listener's choice and goes with
  `autoplay: true`. `nativeQueue.adopt()` still runs on mount, so a restored list identical to the
  service's is not pushed at all.
- **Mini player / wide bar**: `{:else if restoringQueue}` shows `Throbber` in a `bg-muma-skeleton`
  cover slot and `player.restoringQueue` ("Wachtrij wordt hersteld…").

## Why nothing half-done reaches the service

The only path from the UI's queue to `PlaybackService` is the queue sync effect in `Player.svelte`
(`nativeQueue.sync` -> `MumaPlayer.setQueue`). While a restore runs it returns early, whatever the
stores hold. Native command/duration reports cannot write a stale track meanwhile either:
`trackAfterCommand` looks the reported id up in the UI queue, which is empty until the restore
writes it, so it answers null.

## Cross-App Impact

Frontend only, but the APK bundles the web UI: the behaviour reaches phones only with an app
release (`versionCode` bump in `services/muma-mobile/app/build.gradle`). No Kotlin change: the
plugin's `setQueue`/`queueState` contract is untouched.

## Technical Acceptance Criteria

1. `bootstrapShell(..., {deferQueue: true})` resolves while every `getSong` is still pending, with
   `queueRestore.status === 'restoring'` and empty queue stores (`tests/unit/nativeSession.test.js`).
2. Releasing the lookups fills `playlist`/`currentTrack`/`playerState` and sets `restored`.
3. A `currentTrack` write during the restore sets `cancelled`; the late result is dropped and
   `queueRestored` resolves to 0.
4. A `playlist` edit without a track keeps the restore running and its tracks end up last.
5. A service with an empty queue gets the `localStorage` queue back in the stores.
6. Mounted during a restore, `Player.svelte` calls `setQueue` zero times; a finished restore equal
   to the service's queue is not pushed; a differing one is pushed with `autoplay: false`; a track
   started during the restore is pushed once with `autoplay: true` and the late restore pushes
   nothing (`tests/unit/playerQueueRestore.test.js`). Removing the guard fails these tests.

## Related Docs

- [perceived-performance](../perceived-performance/functional.md) (#107), where this was left open.
- `services/frontend/src/lib/nativeQueue.js` for the three queue hand-off rules.
