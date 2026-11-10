# App start: server reachability and offline mode — Technical Design

Implements [`functional.md`](functional.md). Android app only (`services/muma-mobile` and the Svelte bundle
it serves from `services/frontend`); no server change, no browser change.

## Data Model

No database change. Two pieces of client state:

- **`ServerReachability.offlineChosen`** (Kotlin, `@Volatile`, in memory): the listener chose
  "Offline verder" in this process. Not persisted — the next cold start asks the server again.
- **`muma_offline_queue_stash`** (WebView `localStorage`): the native queue as it was before an offline
  start cut it down — `{ids, playingId, index, offlineIds}`, first 200 ids. Written only when tracks were
  left out; removed once used. Survives a reclaimed WebView and an app restart, so an online start after an
  offline one still puts the full queue back.

## API Contract

No HTTP endpoint is added. The contract that changes is the Capacitor bridge, `platform.storage`
(`src/lib/platform/index.js`, `MumaStoragePlugin.kt`):

| Call | Request | Response | Error cases |
|---|---|---|---|
| `checkServer` | `{timeoutMs?}` (default 3000) | `{state, elapsedMs, offlineChosen}`; `state` ∈ `reachable`, `noNetwork`, `unreachable`, `authFailed` | Never rejects on a failed ping. A missing method (older APK) or a rejected bridge call is read as `reachable` by `serverReachability.checkServer` (fail open). |
| `setOfflineMode` | `{enabled: boolean}` | — | Rejection is logged; the web side enters/leaves offline mode regardless. |

`isOffline()` now also answers `true` while `offlineChosen` holds, and the `connectivity` event carries the
same. Browser implementation: `checkServer` answers `reachable`, `setOfflineMode` is a no-op. Not a breaking
change: both additions are new methods, and an older APK serving a newer bundle simply skips the check.

### The check (native)

`MumaStoragePlugin.checkServer`: reads `ConnectivityManager` (`NET_CAPABILITY_INTERNET`), sends one Subsonic
`ping` through the app's own `SubsonicAPIClient` (same signing as every other call), enqueued so that the
timeout really cancels the socket (`pingWithin`, `ServerPing.kt`), and classifies with
`ServerReachability.classify(networkUp, outcome)`:

| Ping outcome | Classified as |
|---|---|
| `status: ok` | `reachable` (whatever the network state says — a LAN without internet can still reach the server) |
| failed envelope, code 40–44 | `authFailed` |
| failed envelope, any other code | `reachable` |
| HTTP 401/403 | `authFailed` |
| HTTP 502/503/504 (proxy up, server down) | `unreachable` (`noNetwork` without a network) |
| other non-2xx | `reachable` |
| timeout, network error, unreadable body (captive portal) | `unreachable` with a network, `noNetwork` without |
| no ping (hand-picked offline library) | `reachable` with a network, `noNetwork` without |

`MusicServiceFactory.getMusicService()` returns the offline service while `offlineChosen` holds, without
touching the active server — so the Android Auto tree, voice, downloads and the scrobbler all see the
downloaded library. A scrobble sent to the offline service throws `OfflineException`, which
`ScrobbleDelivery` maps to `RETRY`: listens stay queued (bug report 071) and go out when the server is back.

### The start (web)

`bootstrapShell` (`nativeSession.js`):

1. `report("connecting")`, start `checkServer(platform)` **without awaiting it**, then `applyServerUrls`.
2. `decideStart`: a phone without a session (signed out, or after a deliberate logout) never waits for the
   check. Otherwise await it and log `shell:reachability {state, elapsedMs, skipped}` to the diagnostics trail.
   - not unreachable → online (and `setOfflineMode(false)` if the process was still offline);
   - unreachable and `offlineChosen` already → offline without asking (a rebuilt WebView);
   - unreachable → `decide(check)`, which in the app is `askServerDecision` (`bootUnreachable.js`).
3. Offline: `enterOfflineMode` (native flag, `offline` store, banner store), `report("offlineStart")`, then the
   ordinary `restoreSession` and `rehydrateOfflineQueue`: the same `getSong` per queued id, now answered by
   `OfflineSubsonic` (only files on disk), cut down by `planOfflineQueue` — kept tracks in queue order; the
   playing track if kept, else the first kept at/after the old index, else the last before it; skipped count
   to the banner; full queue to the stash.
4. Online: the unchanged `rehydrateQueue`, then `reconcileQueue` if a stash exists.

`askServerDecision` draws the panel on the boot screen (`#boot-screen.boot-choosing`, CSS in `index.html`),
pauses the boot screen's slow hint and 20 s reload pill (`pauseBootHints`), and resolves `online` or `offline`.
"Wachten op server" runs `waitForServer` (`serverReachability.js`): delays `[2, 5, 10, 20, 30] s` capped at 30,
an attempt at once on a `connectivity` event with `online: true`, never two attempts at a time, ends on the
first answer that is not unreachable.

After mount, `watchServerReturn` (`offlineMode.js`) runs `waitForServer` (with `anyChange`, because the device
reports offline while the choice holds) whenever offline mode is on. On an answer: `leaveOfflineMode`, then
`reconcileQueue` — only when the web queue still equals `stash.offlineIds`, fetch the full queue from the
server and `startQueue` it; `currentTrack` is left alone, so `queuePlanFor` rebuilds around the playing item
instead of reloading it. A toast reports the result. The banner's "Opnieuw verbinden" is `retryNow()` on the
same loop.

### Cost in the normal case

The ping leaves in the same turn as `applyServerUrls` and runs on a native IO thread; the start waits for it
only after the server URLs and the phone's credentials are read. Added latency is at most one ping round
trip on the LAN minus that overlap. Measured per start as `elapsedMs` in the `shell:reachability`
diagnostics line; the on-device number is part of the verify issue.

## Cross-App Impact

`services/frontend` (bundle, boot screen) and `services/muma-mobile` (plugin, service factory) change together
in this MR, as the bridge contract requires. The browser build is unaffected: `bootstrapShell` returns at once
outside the shell, and the browser storage answers `reachable`. Frontend changes need an app version bump at
release.

## Technical Acceptance Criteria

1. `ServerReachabilityTest` (JVM): every row of the classification table, `outcomeOf`, and `hasRouteToServer`
   with `offlineChosen`.
2. `serverReachability.test.js`: fail-open cases, backoff schedule, connectivity trigger, `anyChange`, one
   attempt at a time, cancel.
3. `bootUnreachable.test.js`: all three buttons, the waiting countdown, give up waiting, connectivity trigger,
   `authFailed` → online, no boot screen → offline.
4. `offlineMode.test.js`: `planOfflineQueue`, enter/leave, `reconcileQueue` (untouched / changed / none), and the
   background return.
5. `nativeSession.test.js`: reachable and `authFailed` never ask; signed-out never asks; "wait" continues online
   with the full queue; "offline" restores only downloaded tracks without any server `getSong`; an already
   offline process stays offline; an online start with a stash puts the full queue back.
6. The emulator smoke test (wiped data, signed out) still reaches the login page: a signed-out phone never
   waits for the check.

## Not covered (follow-ups)

Both are built in [`offline-followups/`](../offline-followups/technical.md) (#149): Android Auto outside
offline mode, and a durable rating queue.

## Related Docs

- [`perceived-performance/`](../perceived-performance/) — the boot screen this panel lives on.
- [`universal-ui/`](../universal-ui/) — the offline library (`OfflineSubsonic`) and the `subsonic.js` switch.
- Issue #113 — mounting before the queue restore; independent of this change.
