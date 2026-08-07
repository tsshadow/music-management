# Radio Mode

Radio mode is a server-owned broadcast: one programme, many listeners, nobody in
control. It is a beta feature — it ships in the release, but expect rough edges.

## The virtual timeline

The server does not stream audio. It publishes a *timeline*: rows in
`radio_timeline` laid back to back, each carrying a `track_id`, a `duration_ms`,
and an absolute `started_at` and `ends_at` in epoch seconds on the server's
clock. Clients read that timeline and stream the individual tracks from LMS
themselves.

This is the key design decision, and it is why the old attempt at this behaved
badly. The previous implementation stored a *position* ("we are 42 seconds into
this track"), which is only true at the instant it is written and rots
immediately: a listener joining three minutes later would jump back to second
42. A `started_at` never rots. Position is derived, never stored:

```
position = serverNow - started_at
```

Pausing is not expressible on a radio channel, which is the point — a radio
station does not pause because one listener stopped listening.

The upshot is that the channel plays whether or not anyone is tuned in, needs no
host device, and a late joiner lands in exactly the right spot.

## Clock offset

`position = serverNow - started_at` needs `serverNow`, and a client only knows
its own clock, which can be seconds off. So each client measures the offset
against `GET /api/radio/time`, which is deliberately DB-free so its latency is
small and stable:

```
offset = serverTime - (t_before_request + t_after_response) / 2
```

Five samples are taken and the **median** is used, so one slow round trip cannot
drag the estimate. The offset is re-measured every five minutes, because clocks
drift over a long listening session. The `server_time` in the state response is
deliberately *not* used for this: that endpoint hits the database, so its
latency is unknown and a single sample from it would be worse than the median.

## Drift correction

Even anchored correctly, a client drifts: buffering, decoder timing, a laptop
suspending. Correction is two-tier, and the split is what makes it feel smooth
rather than jumpy:

- Error above **3 seconds**: reload the stream at the correct offset. Audible,
  but at that size the alternative is worse.
- Error between **0.15 and 3 seconds**: nudge `playbackRate` between 0.98 and
  1.02 until the error closes. Inaudible.
- Error below **0.15 seconds**: do nothing.

The same thresholds and the same maths exist twice, once in
`services/frontend/src/lib/radioSync.js` and once in
`RadioSync.kt` for Android, so both clients land on the same point in the track.
If you change one, change the other.

## Streaming, and why `format=mp3` is mandatory

Joining mid-track means asking LMS for the track from an offset. LMS supports
`/rest/stream?timeOffset=N`, but **only on its transcoding path** — see
`MediaRetrieval.cpp:136` and `:226`, and the explicit `// TODO: what if offset is
not 0?` at line 147 covering the raw path. A radio stream URL must therefore
always carry an explicit `format`, or the offset is silently ignored and every
listener starts every track from the beginning.

On Android this is why `MusicService.getTranscodedStreamUrl` exists. The older
`getStreamUrl` accepts `maxBitRate` and `format` and then drops them on the
floor (`RESTMusicService.getStreamUrl` calls `API.stream(id)` with no
parameters), which would have hit exactly this trap.

## The scheduler

`run_radio_scheduler` runs as a daemon thread next to the tagger and scanner
loops. Every five seconds it checks each enabled channel and, if the timeline is
not filled at least ten minutes past now, pulls a batch of candidate tracks from
LMS and appends them back to back. Entries older than an hour are deleted.

If LMS is unreachable the iteration logs and returns; the timeline simply stops
growing and resumes when LMS comes back. If the timeline has fallen entirely
into the past (the service was down for a while) the scheduler resumes from now
rather than replaying history.

`plan_entries` — the part that decides where entries land — is a pure function
with no database or HTTP in it, which is where the scheduling behaviour is
tested. `pick_candidates` sits just before it and decides *which* candidates may
be scheduled: for now only dropping tracks still on the timeline, so a channel
with few matches cannot repeat itself inside one ten-minute window. It is the
one place a weighted selection ("better songs more often") would land.

## Channels

A channel is a stored library filter. `radio_channels` has a `slug`, a display
`name`, and a `filter_json` holding any of `label`, `genre`, `artist`, `length`,
`year`, `rating_min`, `rating_max`, `duration_min`, `duration_max` and
`include_unrated`. Everything absent means "do not filter on this", so an empty
filter is the whole library — which is what the seeded `main` channel is.

The scheduler asks LMS for candidates through one endpoint,
`/rest/getSongsByFilter`, whatever the channel is. It is our own addition to the
Subsonic surface (`AlbumSongLists.cpp`), and it only exposes filtering LMS
already had: `db::Filters` carries a `LabelId`, `Track::FindParameters` carries
`artistName`, duration and rating bounds, and YEAR/LENGTH are clusters. Results
come back randomised server-side, so unlike the old `getSongsByGenre` path there
is nothing to shuffle client-side.

A label and a publisher are the same thing here, read from the same tag on both
sides: our scanner stores `song.publisher()` in `library_labels`, and LMS maps
`TagType::RecordLabel` to `LABEL`, `PUBLISHER` and `ORGANIZATION`
(`audio/impl/taglib/TagReader.cpp`). So the names in the management screen's
label picker are the names LMS knows, and nothing needs reconciling between the
two. Two smaller mismatches are still possible, and the filter preview is how
you spot either:

- LMS hangs the label on the *release* and filters tracks through
  `release_label` on `t.release_id`, so a track LMS never grouped into a release
  is unreachable by a label channel however well tagged its file is.
- LMS splits a multi-valued tag on its configured delimiters while the scanner
  keeps the publisher string whole, so `Foo;Bar` is two labels there and one row
  here.

Ratings are per-user, resolved against whichever user the scheduler's API key
belongs to. `include_unrated` decides whether a channel with a rating floor
still plays tracks nobody has rated — it defaults to off, because a rating
filter that quietly includes unrated tracks is not a rating filter.

The older nullable `genre` column still drives any channel created before
`filter_json` existed. Editing a channel's filter clears it, so the two can never
disagree about what a channel plays.

Channels are created and edited from the management page (`RadioTab`), behind a
`radio.manage` permission. That screen can preview a filter — how many tracks
match, plus a sample — before saving, which is also how a label name that LMS
does not know gets caught. The web player offers a channel picker when more than
one channel is on air, and tunes straight in when there is only one.

## Transport

Everything is plain HTTP polling: state every 10 seconds, correction ticks every
2 seconds against the local clock without a request. This is not a placeholder
for a "real" push transport — a timeline that only changes at track boundaries
does not benefit much from one — but it is also a deliberate constraint. Clients
reach the backend through the LMS `/muma` proxy
(`services/music-management-server/src/libs/muma/MumaResource.cpp`), which is a
buffered request/response proxy with no WebSocket or SSE support. Adding push
would mean a new nginx route straight to `music_manager`, not just a client
change.

The transport is isolated in `radioController.js` and `RadioPlaybackController`,
so swapping it later touches one function per client.

## What radio is not

Radio is not Jam. Jam is a shared session with a host device and guests who can
steer it; radio has no host and no steering. They share the clock-offset and
drift maths and nothing else. Jam still coordinates over the per-user Subsonic
play queue, which means it only works between devices logged in as the same
user — rebuilding it on a proper session resource is separate work.

Radio also cannot crossfade, run jingles, or carry a live DJ, because each
listener plays its own file copy. If that is ever wanted, the answer is a real
broadcast (Icecast/Liquidsoap), which would replace client-side synchronisation
rather than extend it.

## Known dead code

`services/music-management-server/src/lms/ui/spotify-ui/` still contains an
older copy of the player with its own boolean `radioMode`. Nothing builds it —
`Dockerfile-release` copies `services/frontend` — and it is unrelated to this
feature. It should be deleted wholesale rather than edited.
