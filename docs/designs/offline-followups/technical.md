# Offline mode follow-ups: Android Auto and queued ratings — Technical Design

Implements [`functional.md`](functional.md). Android app only: `services/muma-mobile` and the
Svelte bundle it serves from `services/frontend`. No server change, no change for a browser.

## Data Model

No database change. Client state:

- **`ServerReachability.lastCheck`** (Kotlin, `@Volatile`, in memory): `ServerCheck(state, atMs)`,
  the newest native check. Written by `checkServerNow` (`ServerPing.kt`), which both the web's
  `checkServer` bridge call and the car run.
- **`muma_pending_ratings`** (private `SharedPreferences`, key `queue`): the rating queue, one
  `PendingRating(trackId, serverId, rating, ratedAtMs, attempts)` per line, tab-separated
  (`PendingRatingCodec`). Plain text and not Gson for the reason `PendingScrobbleCodec` gives: R8
  renames fields between builds. A line that does not parse is skipped.

### The rating queue (`PendingRatings.kt`)

| Rule | Where |
|---|---|
| One entry per `serverId\|trackId`. A new rating replaces the old one and moves to the end: the last rating wins. | `PendingRatingQueue.record` |
| Due: entries of the active server, plus entries without a server (`-1`, given while the offline library was active). | `due` |
| Entries older than 30 days are dropped; above 5000 entries the oldest goes. | `due`, `record` |
| An entry is removed after a send only while it is still the newest of its track, so a rating given during the send goes out next. | `done` |
| A send outcome is judged by `ScrobbleDelivery.outcomeOf`: "not found" and "missing parameter" are final, everything else (an `OfflineException`, a timeout, a 5xx) is retried. A pass stops at the first retry. | `RatingDelivery.flush` |

## The One Rating Path

A rating has three copies in the app (`MediaItemConverter.trackCache`, the `userRating` extra and the
`StarRating` in the immutable `MediaMetadata`, see bug report 024), plus the web's own `ratings` store.
Every native rating already ends in `RatingManager.submitRating`: the phone's controls through
`RxBus.ratingSubmitter`, the car through `MediaLibrarySessionCallback.onSetRating`. The queue lives
there, so nothing new writes a rating anywhere else:

1. `submitRating` drops a repeat of the last update, ignores an unrated `StarRating`, writes the entry
   to the queue, calls `MediaItemConverter.applyRating` (so a rebuilt `MediaItem` shows the new value
   while it waits) and starts a flush.
2. The flush sends through `getMusicService().setRating`. Online that is `CachedMusicService`, which
   corrects the cached directories, home lists and `MediaItemConverter` after the server stored it,
   as before. In offline mode it is `OfflineMusicService`, whose `OfflineException` keeps the entry.
3. `RxBus.ratingPublished` is sent per tried entry, with `success`.

Flush triggers: the manager starts (with `PlaybackService.onCreate`, so a car-only process sends an
old queue), every new rating, a reachable native check or the end of offline mode
(`ServerReachability.addReachableListener`), a network that becomes available, and a back-off timer
(30 s, doubling to 15 min) while entries are left. Sends run one at a time
(`Dispatchers.IO.limitedParallelism(1)`).

### The web rating path

The app's UI is the web bundle, which writes ratings itself with `fetch` (`ratings.js`). It hands a
rating to the native queue through `platform.storage.queueRating(id, rating)` when:

- offline mode is on (`offline` store): no request is made;
- the request never reached the server: `fetch` threw, or the answer was 502, 503 or 504;
- the same track was queued earlier in this session: so the queue never sends an older value after a
  newer direct write.

The stars stay on screen and `notify.info("notify.ratingQueued")` is shown. A Subsonic error in the
body, or any other HTTP status, is the server's answer and rolls back as before.

## Android Auto

`MediaLibrarySessionCallback.musicService` (the one getter the car's data provider, browser and
playback controller resolve per call) asks `CarServerCheck.prefersOffline()`. True gives
`MusicServiceFactory.getOfflineMusicService()`, false the unchanged `getMusicService()`.
`getMusicService()` itself is not changed, so downloads, the scrobbler, the rating queue, the token
refresher and voice outside the session keep their behaviour.

`CarServerCheck.route(offlineChosen, lastCheck, nowMs)`:

| Situation | Browse | Check again |
|---|---|---|
| offline mode chosen | offline | no, the web's own loop asks |
| no check yet | online | yes |
| unreachable or no network, younger than 2 min (`TRUST_MS`) | offline | when older than 20 s (`RECHECK_MS`) |
| unreachable, older than 2 min | online | yes |
| reachable or refused credentials | online | when older than 2 min |

A check again runs in the background on `serviceScope`, one at a time, so a browse call never waits.
`onGetLibraryRoot` calls `ensureFresh()` first: when the last answer is missing or older than 20 s, it
runs one check (3 s budget, `checkServerForCar`) before it answers. That is the cold start in the
car. The check is the same `checkServerNow` the web uses: Android's network state plus one signed
`ping`, classified by `ServerReachability.classify`.

The session also serves controllers other than the car (Assistant voice requests and
`onAddMediaItems`). They follow the same route, which is the wanted answer when the server is down.

## API Contract

No HTTP endpoint is added. The Capacitor bridge `platform.storage` gets one method:

| Call | Request | Response | Error cases |
|---|---|---|---|
| `queueRating` | `{id, rating}`, rating 0 to 5 (0 clears) | `{queued: true}` once the entry is in the queue | Rejects a blank id or a rating outside 0 to 5. An older APK without the method rejects; `ratings.js` reads that as "no queue" and rolls back. Browser: resolves `false`. |

Not a breaking change: a new method, and an older bundle never calls it.

## Cross-App Impact

`services/frontend` (`ratings.js`, the platform bridge, two i18n strings) and `services/muma-mobile`
change together in this MR, as the bridge contract requires. The browser build keeps its behaviour.
The app picks up both halves only from a new APK.

## Technical Acceptance Criteria

1. `PendingRatingsTest` (JVM): codec round trip and bad lines, last rating wins, per-server entries,
   `due` filter and age limit, size limit, `done` keeps a newer rating, delivery order, stop on
   retry, "not found" dropped.
2. `RatingManagerTest` (Robolectric): ratings 0, 3 and 5 reach `setRating` and never `star`/`unstar`;
   an offline failure keeps the entry, and after two ratings of one track only the last reaches the
   server; a queue from an earlier process is sent on start; an unrated `StarRating` sends nothing.
3. `CarServerCheckTest` (JVM): every row of the route table; `ensureFresh` checks only when the last
   answer is old or missing and never in offline mode; a background check runs once and its answer
   is used on the next call; a failing check changes nothing.
4. `ServerReachabilityTest`: `record` stores the check; a reachable answer, or leaving offline mode,
   tells the listeners; not while offline mode holds; a failing listener does not stop the others.
5. `ratings.test.js`: offline mode queues without a request; a clear is queued as 0; a network error
   and a 502 queue; a refusal rolls back without queueing; an APK without the method rolls back; a
   later rating of a queued track goes to the queue too.
6. `platform.test.js`: the browser answers `false`; the Capacitor bridge passes `{id, rating}` and
   reads `queued`.

## Related Docs

- [`app-start-reachability/`](../app-start-reachability/): the start-up check, offline mode and the
  first part of the Android Auto offline tree.
- [`mobile-scrobbling/`](../mobile-scrobbling/technical.md): the scrobble queue this queue copies.
- [`ratings-scrobbling/`](../ratings-scrobbling/): the rating scale.
- Bug reports 024 (the three rating copies) and 071 (durable scrobbles).
