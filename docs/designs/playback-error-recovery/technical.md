# Playback Error Recovery — Technical Design

Implements [functional.md](functional.md).

## Where the error was handled

`PlaybackService` owns the ExoPlayer and the `MediaLibrarySession`. Its player listener had no
`onPlayerError`, so ExoPlayer went to `STATE_IDLE` with `playerError` set, and the session sent
that error to every controller. Android Auto showed it as a play error. The only `onPlayerError`
was in `MediaPlayerManager`, the app-side `MediaController` listener. It sends the error to the
web player (`RxBus.playerErrorPublisher`) and switches the jukebox off. It does not exist when the
app UI was never opened, which is common in the car.

The recovery is therefore in `PlaybackService`, on the session's player. The car, the notification
and the app all control that one player.

## Data Model

No database change. The state is in memory, per service:

- `PlaybackErrorRecovery` (`services/muma-mobile/.../service/PlaybackErrorRecovery.kt`) keeps the
  entry that already had its retry (`Entry(index, mediaId)`) and the count of entries in a row that
  failed after their retry.
- An entry is a place in the timeline, not a track: the same track twice in a queue is two
  entries.

## Decisions

`PlaybackErrorRecovery.onError(entry, hasNext)` returns one step:

| State | Step |
|---|---|
| The entry has not had its retry. | `Retry` |
| The entry had its retry, and this makes `MAX_FAILED_ITEMS` (3) failed entries in a row. | `GiveUp(TOO_MANY_FAILURES)` |
| The entry had its retry, and there is no next entry (`Player.hasNextMediaItem()`, with repeat and shuffle applied). | `GiveUp(END_OF_QUEUE)` |
| The entry had its retry, otherwise. | `Skip` |

The state changes on these player events:

- `onIsPlayingChanged(true)` sets the failed count to zero. The retry of the current entry stays
  used, so an entry that plays after its retry and fails at the same spot again is skipped and not
  loaded a third time.
- `onMediaItemTransition` to another entry forgets the retry. A transition with reason
  `PLAYLIST_CHANGED` (a new queue) clears all state.
- A give-up clears all state, so play after a stop is a new first attempt.

## What each step does in `PlaybackService`

- `Retry`: for a library track (`PlaybackServiceRules.isLibraryTrack`, not radio, not news), on
  the IO dispatcher: delete the `.complete` cache file and queue a download with
  `DownloadService.download(isHighPriority = true)`. A pinned file is never deleted, and offline
  mode deletes nothing. Then, on the main thread: `seekTo(index, position)` and `prepare()`. With
  no cache file, `CachedDataSource` passes the load to the resolver, which streams it. The reload is
  left out if the player is on another entry or has no error any more by then
  (`player.recover.stale`).
- `Skip`: `seekToNextMediaItem()` and `prepare()`. `playWhenReady` stays as it was.
- `GiveUp`: `playWhenReady = false`. The error stays on the player. Media3 clears an error only on
  the next `prepare()`, and a prepare would load the failed entry again.

The jukebox backend is left out: it plays on the server, and `MediaPlayerManager` already switches
it off on an error.

## Diagnostics

Every error writes `action player.error | code=<ERROR_CODE_NAME> | index=<n> | id=<media id> |
step=<retry|skip|give-up-end_of_queue|give-up-too_many_failures>`. The retry writes
`player.recover.drop` when it deletes a file, and `player.recover.reload` or
`player.recover.stale`.

## API Contract

No API change.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| None | | | |

## Cross-App Impact

MuMa Mobile only. The web player inside the app still gets each error through
`MediaPlayerManager` and shows its "stream failed" message, also when the recovery then plays on.

## Technical Acceptance Criteria

1. `PlaybackErrorRecoveryTest` pins every row of the decision table, the reset on play, the reset
   on give-up, a repeated track as two entries, and "repeat all" on one dead track stopping after
   three failures.
2. `PlaybackServiceRulesTest` pins which item URIs have a cache file to drop: a library track yes,
   a radio URL and a news bulletin no.
3. Not covered by an automatic test: the calls on a real ExoPlayer and the behavior in a car. That
   needs a check on a device.

## Related Docs

- `services/muma-mobile/app/src/main/kotlin/nl/teunschriks/mumamobile/data/CachedDataSource.kt`:
  the choice between a cached file and the stream.
