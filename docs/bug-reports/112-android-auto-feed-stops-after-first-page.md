# title: Android Auto stops a feed after its first page

# status: fixed

# reported problem
GitLab issue #84. Since MR !1050 (release 0.78.0, docs/designs/feed-length/) a feed is 100 tracks by
default and continues past that: `GET /api/feeds/{slug}` pages with `offset`/`limit` and returns
`next_offset`. The web player and the MuMa Mobile shell top a feed queue up near its end
(`services/frontend/src/lib/feedQueue.js`), but a feed played from Android Auto -- "Alles afspelen"
in a feed folder, or a tapped track -- played the first page and then stopped.

# Possible reason
The native path never asked for a second page. `FeedRepository` fetched `GET /api/feeds/{slug}`
without `offset` and dropped `next_offset` (the `MumaFeed` model had no such field), and nothing on
the media3 side watched the queue approaching its end: the car's queue was the first page, handed
to the player once in `onAddMediaItems` / `onSetMediaItems`, and nothing ever appended to it. The
feed-length technical design listed this explicitly as out of scope ("No continuation in the car").

# solution
Design: [docs/designs/feed-length/technical.md](../designs/feed-length/technical.md), section
"Continuation in Android Auto".

- `MumaFeed.nextOffset` and an `offset` query parameter on `getFeed`; `FeedRepository.firstPage`
  (the cached day's list plus `nextOffset`, what `tracksFor` answered before) and `pageAfter(slug,
  offset)` (never cached, null on failure).
- `FeedQueueContinuation` (service/androidauto): armed by the two car paths that start a feed queue
  (`playAllFromFeed` for "Alles afspelen", `queueFromTap` for a tapped feed track, via
  `CarQueue.feedSlug`/`feedNextOffset`) and stopped by every other queue replacement
  (`onSetMediaItems`, a search, radio, the legacy path). `PlaybackService`'s player listener calls
  `onQueueMoved` on every track change and playlist change; within 3 tracks of the end in play
  order the next page is fetched on IO and appended on the main thread through the session's own
  player (`PlayerFeedQueue`, which checks `COMMAND_CHANGE_MEDIA_ITEMS`). One request at a time; a
  failed page keeps the offset for the next track change; `next_offset: null` ends it; only ids
  neither in the feed so far nor in the queue are appended, and a page of nothing but repeats is
  followed by the next one (at most three per top-up); a page that arrives after the queue was
  replaced is dropped. Radio and news are never extended.
- The car's feed folder lists at most `DISPLAY_LIMIT` (100) tracks, since the stored list can reach
  500 once the web has continued it.
- Tests: `FeedQueueContinuationTest` (trigger, append, stop at null, duplicates, no double fetch,
  failure retry, replaced queue), `FeedRepositoryTest` (paging), `MediaLibraryTapQueueTest` (a tapped
  feed track carries its continuation).
