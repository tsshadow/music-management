# Feed length — Technical Design

Implements [functional.md](functional.md). GitLab issue #83.

## Data Model

No schema change. `feeds_snapshot.payload` (LONGTEXT JSON) carries two more things:

- the tracks list may grow during the day, as continuations are appended to it (see below);
- `exhausted` (bool, stored, never sent): set when a build ran out of candidates — it came out
  short of its size *and* the quota could not hand out that many places (`_ran_out`; short only
  because the per-artist cap removed a few does not count) — or when a continuation found nothing
  new. Later requests stop building. A 40-track feed that only had 40 candidates never costs a
  continuation build just to learn that.

Each track in the payload gains `work_id` (the song the track belongs to, or null for an ungrouped
track). It is what a continuation compares against, so "no repeats" means no repeated *song*, the
same collapse `build._collapse_to_songs` applies within one build.

## The length setting

`feeds_size` — integer, ConfigStore group `Feeds`, env `FEEDS_SIZE`, default 100. Parsed by
`policy.parse_feed_size`: a value outside 10–200 or not a number falls back to 100. The router
applies it to every policy through `resize` (below; `routers/feeds.py`, `_sized`), so
`FeedPolicy.size` stays the code default and a tuned value never needs a release. The parsed size is
part of `params_key`, so changing it ages every stored snapshot and the next read rebuilds.

A length change goes through `policy.resize(policy, size)`, never a bare `replace`: a policy whose
per-artist cap equals its size is uncapped by construction — the artist mix, where every candidate
shares one artist (bug report 110, issue #77) — so its cap moves with the size; every other cap (3)
stays. The dry run (`scripts/feeds_dryrun.py --size`) and a continuation's bigger build use the
same helper.

`MIN_BAND_CANDIDATES` and `MIN_ROTATION_CANDIDATES` (both 15) stay fixed floors and do not scale
with the length. They answer "is this slice worth serving at all", not "can it fill the mix":
scaled to half of 100 (50), the artist mix would skip nearly every name in a listener's top ten
(production 2026-09-26: the drawn artists had 0–3 playable songs at 90 days) and the spectrum
bands would widen their window on days they fill without it. A band that stays short of 100 still
fills from unknown hardness (`_backfill_from_unknown`), and an artist mix of 15–99 songs is a
complete mix of that artist.

Upper bound 200 because LMS's `getSongsByPath` accepts at most 100 paths per call
(`SongsByPath.cpp`, `maxPathCount`); both clients now resolve paths in chunks of 100, so anything
above 100 costs one extra round trip per 100, not an error.

## Continuation

`GET /api/feeds/{slug}?offset=N&limit=M` serves the window `[N, N+M)` of the day's list.

1. The day's snapshot is read (or built) exactly as before — `snapshot.serve`.
2. When the window reaches past the stored list, the feed is `ok`, not `exhausted`, and the list is
   shorter than `MAX_FEED_LENGTH` (500), the list is extended under the snapshot's per-key lock
   (`snapshot.extend`):
   - the feed is built again at `size = stored + max(size, wanted - stored)` (capped at 500) —
     the same ranker, profile, exclusions, quota and per-song collapse, just more places;
   - every track whose song (`work_id`, else the track id) is already in the stored list is
     dropped; what remains, in the build's order, is appended;
   - nothing new, or a build that ran out of candidates → `exhausted: true`;
   - the row is written back with its original `generated_at` and `params_key`, so extending a
     radar does not also extend its hourly freshness.
3. The response is the stored body with `tracks` sliced to the window, plus `offset` and
   `next_offset` (the offset of the next page, or null when the list is exhausted or at 500).

**A split daily mix continues from a stored reserve** (issue #137). Klassiek, Zachter/Middenin/Harder
and the label mix build from two library samples (docs/designs/daily-mix-older-tracks/) that were
the expensive part of a build, so their head build also ranks the same candidates for
`MAX_FEED_LENGTH` places (`build_feed(reserve_size=500)`, steps 6-8 only, no query) and stores what
that longer list holds beyond the head as `reserve` in the row. A continuation then builds nothing:
it takes the next `max(size, wanted - stored)` songs off the reserve, skipping any song already
stored, writes the row back and is `exhausted` once the reserve is empty. Same superset rule as
below, paid for once in the background; `reserve` is never sent to a client. Release Radar and the
artist mix still continue with a build; a row stored before this change has no `reserve` and does
too.

A continuation is a superset build rather than "the rest of the first build" because the quota is
allocated over the number of places: a 200-place build is not a 100-place build with 100 more
appended. Filtering by song keeps the first page untouched and the second page free of repeats.
The per-artist cap (3) applies within each build; across the stored page and its continuation an
artist can reach 6. Accepted: with 100 places per page, three per artist per page keeps the page
varied, and the cap exists against one artist dominating what the listener sees at once.

Stability: a continuation is stored, so asking for the same window twice on one day answers the
same tracks. Release Radar is rebuilt hourly (`RADAR_TTL_SECONDS`), which drops its continuations
with it; the clients dedupe by track id on append, so an extension across such a rebuild never
shows a track twice either.

Backwards compatible: without `offset` the request is what it was — `limit` (now 1–100) takes the
head of the list, no `limit` returns the whole stored list. The old "`limit` larger than the
policy's size builds a live, unstored feed" path is gone; that request is now a stored
continuation.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/feeds/{slug}` | `offset` int ≥ 0 (default 0), `limit` 1–100 (default: the rest of the stored list at offset 0, else the configured length) | existing body + `offset` (int), `next_offset` (int or null); tracks carry `work_id` | 404 unknown slug, 422 bad `offset`/`limit`, 400 system key without `username` |
| `GET /api/feeds` | unchanged | `size` per feed is the configured length | unchanged |

Additive only; no breaking change.

## Performance

Measured on production (functional.md): a build costs the same at 30 and at 100 (Release Radar
4.1 s both) — the profile and candidate queries dominate, not the number of places. The exception
is Middenin/Harder, which at 100 run short of in-band candidates after the artist cap and take the
existing unknown-hardness backfill (`_backfill_from_unknown`): 22 s instead of about 5 s. The nightly
refresh is a background thread over 3 active listeners, so about +35 s per listener per day, about
two minutes in total. A continuation is one extra build on demand (4–23 s), at most four per feed
per day (500 / 100). A split daily mix's continuation is a read and a write-back of its own row since
issue #137 -- no build, milliseconds instead of the two library samples (~11 s before, ~4.5 s after
that issue's query rewrite). Response size: about 0.5 KB per track, so a 100-track page is about 50 KB.

## Cross-App Impact

One MR (AGENTS rule 7):

- **music-manager**: setting, `offset`/`next_offset`, snapshot extension.
- **frontend** (web and the MuMa Mobile shell, same bundle): `feeds.js` reads pages and resolves in
  chunks of 100; `FeedView.svelte` shows "Meer laden"; `startQueue(..., { continuation })` plus
  `feedQueue.js` top up a queue started from a feed (Player's effect, once the current track is within three of the end;
  the native queue follows the `playlist` store as for "add to queue").
  Since bug report 122 (issue #97): a queue started by tapping a row of the feed list carries the
  continuation as well (`TrackList`'s `continuation` prop), not only one started with the play
  button. The queue list ends in "Meer laden" while its feed has a next page
  (`QueueFeedLoadMore.svelte`, `extendFeedQueue({ force: true })`). `loadFeedDetail`/`loadFeedPage`
  report `unresolved`, the paths LMS had no song for. The feed header shows that count, and the
  list leaves those rows out. `next_offset` keeps counting MuMa's rows, so a gap never shifts a
  page.
  Since issue #100 the top-up is generic ([`docs/designs/list-continuation/`](../list-continuation/technical.md)):
  `feedQueue.js` only builds a feed's continuation (`feedContinuation(slug, nextOffset)`), the
  top-up is `listContinuation.js` `extendQueue`, and the queue pill is `QueueLoadMore.svelte`,
  shared with every other paged list.
- **MuMa Mobile native (Android Auto)**: `FeedRepository` gets the configured length without
  asking (it never sent `limit`), and resolves paths in chunks of 100 so a length above 100 works.
  A feed queue started in the car continues too, since issue #84 — see the next section.

## Continuation in Android Auto

Issue #84, bug report 112. The car does not run the web bundle, so `feedQueue.js` never sees its
queue; the native side applies the same rule to the media3 player.

- **Paging.** `MumaFeed.nextOffset` (`next_offset`) and an `offset` parameter on `getFeed`.
  `FeedRepository.firstPage(slug)` is what `tracksFor` always fetched — no `offset`, no `limit`, so
  the day's whole stored list, cached per server and day — plus its `nextOffset`.
  `pageAfter(slug, offset)` asks for the page at a handed-out offset (default `limit`, the
  configured length), is never cached (the server stores continuations, and a rebuilt radar must
  answer its new list), and answers null on failure so the caller retries instead of concluding
  the feed ended.
- **Arming.** `ListQueueContinuation` (in `service/androidauto`; `FeedQueueContinuation` until
  issue #103 generalised it to the car's own lists, see
  [`list-continuation/technical.md`](../list-continuation/technical.md#android-auto)) belongs to
  one queue. A feed is its `FeedListSource`. It is armed by the two car paths that start a feed
  queue — "Alles afspelen" (`MEDIA_FEED_ID`, `queueForPlayAll` in `onAddMediaItems`) and a tapped
  feed track (`queueFromTap`, which gets the source and `nextOffset` from `CarQueue.continuation`)
  — and stopped by every other queue replacement:
  `onSetMediaItems` (except a voice "play next", which inserts), a voice search, radio, the legacy
  `onAddMediaItems` path. A first page with `next_offset: null` arms nothing. The state is in
  memory: a feed queue restored after the service was killed plays but does not continue.
- **Trigger.** `PlaybackService`'s player listener calls `onQueueMoved` on every
  `onMediaItemTransition` and every `TIMELINE_CHANGE_REASON_PLAYLIST_CHANGED`. When the current
  item is one of the feed's and fewer than `EXTEND_WHEN_LEFT` (3, the web's value) items follow it
  in play order (the timeline's next-window walk, shuffle included, repeat ignored), the next page
  is fetched on `Dispatchers.IO`. Radio and news own the player while they run and are never
  extended; a bulletin that interrupts a feed queue simply pauses the top-up, because its item is
  not one of the feed's.
- **Append.** Back on the main thread, only tracks whose id is neither in the feed so far nor in
  the queue now are appended (`Player.addMediaItems`, media id = track id). A page of nothing but
  repeats — a radar rebuilt within the hour, a day rolled over at midnight — is followed by the next
  one straight away, at most `MAX_PAGES_PER_TOP_UP` (3) per top-up. `next_offset: null` ends the
  continuation.
- **One request at a time.** A top-up in flight blocks another; a failed page keeps the offset
  and the next track change tries again; a page that arrives after the queue was replaced is
  dropped (a generation counter bumped by every `start`/`stop`).
- **Command grants.** The append calls the player the session was built with, not a
  `MediaController`, so the controller grant rule (media3's default `onConnect` returning an empty
  command set) does not apply; the player's own `COMMAND_CHANGE_MEDIA_ITEMS` is checked, so a
  backend that cannot change its items is logged rather than silently ignored.
- **Browse stays bounded.** The feed folder lists at most `DISPLAY_LIMIT` (100) tracks: the stored
  list reaches up to 500 once the web has continued it, and Auto has item limits of its own. "Alles
  afspelen" and a tapped track still queue the whole first page; continuation is for the playing
  queue, not the list.

## Technical Acceptance Criteria

1. `parse_feed_size` returns 100 for None, '', garbage and out-of-range values, the value otherwise.
2. `params_key` changes when `feeds_size` changes.
3. A request past the stored list appends only tracks whose song is not already stored, writes the
   row back with the original `generated_at`, and marks `exhausted` when nothing new came.
4. `next_offset` is null at the end of an exhausted list and at 500.
5. Frontend: "Meer laden" appends only unseen ids and disappears at `next_offset: null`; a queue
   started with a continuation is extended near its end, one started without is not.
6. Android: a feed longer than 100 paths is resolved in chunks of 100, order kept.
7. Android Auto: a feed queue within three tracks of its end fetches `next_offset` once (not again
   while that request is in flight), appends only ids the feed and queue do not hold, stops at
   `next_offset: null`, keeps the offset after a failed page, and never extends a queue that was
   replaced or is not the feed's (`ListQueueContinuationFeedTest`).

## Related Docs

- [docs/designs/feeds/technical.md](../feeds/technical.md) — the feed algorithm.
- [docs/designs/feeds/home-load.md](../feeds/home-load.md) — snapshots.
