# Daily Mix "Harder" Shows 98 Tracks and No "Meer laden" in the App

# status: fixed

# reported problem
Reported by Teun on 2026-09-27 in the MuMa app (7.8.x, the Capacitor shell running the web UI from
`services/frontend`; on a phone and on a tablet), GitLab issue #97: the daily mix *Harder* shows 98
tracks and there is no "Meer laden" (load more). MR !1050 (0.78.0, `docs/designs/feed-length/`) had
just made a feed 100 tracks long with a paged continuation: a "Meer laden" pill under the feed page
(`FeedView.svelte`) and a queue that tops itself up near its end (`feedQueue.js`, triggered from
`Player.svelte`).

The API was fine on production: `GET /api/feeds/daily-mix-hard?username=user` answered 100 tracks
with `next_offset: 100`, and `offset=98` answered 100 more.

# Possible reason
Three separate things, only one of them in the paging itself.

**98, not 100.** A feed is two lookups: MuMa ranks library paths, LMS turns them into songs through
`getSongsByPath` (`feeds.js`, chunks of 100). LMS answers only the paths it has and simply leaves the
rest out, and the feed page counted what came back. Two of the 100 rows in Teun's snapshot of
2026-09-27 had no song in LMS. Which two could not be settled read-only (the read-only access reaches
MuMa's MariaDB, not LMS's SQLite); the most likely candidates are the two newest files in the page,
added to MuMa's library on 2026-09-26 at 13:45 and 20:16 (`library_tracks` 9720808 and 9733120),
hours before the snapshot was built at 22:12. MuMa's scanner picks a new file up at once; LMS
only has it after its next scan covers that folder. The prefix mismatch known from the rating webhook
(`/music/...` against `/mnt/music/...`) does not apply here: the feed sends `library_path`, which is
relative to the library root on both sides. Nothing said the list was shorter than MuMa's page, so a
100-track mix read as a 98-track one for no visible reason. Paging was not affected: `next_offset`
counts MuMa's rows, not the resolved ones, and the client passed it through unchanged.

**No top-up for a mix started from a row.** Every way a daily mix opens ends in the same place:
the Home card (`DailyMixesShelf` / `DailyMixCard`), the phone's "Daily mixes" page
(`DailyMixesPage`) and the `/daily-mix-*` routes (`router.js`, `Dashboard.svelte`) all render
`FeedView`. There, only the round play button started the queue with the feed's continuation. On a
phone and a tablet (`isMobile`, see bug report 090) a single tap on a row plays it, and
`TrackList.playTrack` called `startQueue(tracks, { name })` without the continuation.
`feedContinuation` was cleared, so `extendFeedQueue` never fired and the queue ended after the
first page. Tapping a track is how most people start a mix.

**Nowhere to load more once the mix is playing.** The queue (the bottom sheet on the phone and the
tablet, the side panel on the desktop) showed the first page and nothing more. The top-up only runs
within three tracks of the end, so while listening there was no visible sign that the feed went on.

The "Meer laden" pill on the feed page itself was rendered whenever MuMa sent a `next_offset`, on
every layout. No CSS, container-query or virtualised-list rule hides it: `TrackList` renders every
row, and the content column scrolls in its own grid row above the player. The new unit tests and
the Playwright check (both layouts, touch pointer) pin that down. The code gives no reason why
Teun did not see it. The likeliest reading of the report is that he was looking at a queue started
by tapping a row, where both gaps above applied.

# solution
- `feeds.js`: `loadFeedDetail` and `loadFeedPage` also return `unresolved`, the number of MuMa's
  paths LMS had no song for. Unresolved rows stay out of the list, because they cannot be played.
  `FeedView` adds them up across pages and says so in the header ("98 nummers • 2 niet gevonden op
  de server"). The count shown is still exactly what can be played. Paging keeps following MuMa's
  `next_offset`.
- `TrackList` takes a `continuation` prop and passes it to `startQueue`. `FeedView` hands over
  `{slug, nextOffset}` and its title, so a queue started from a tapped row continues the feed the
  way one started with the play button does.
- `QueueFeedLoadMore.svelte`: the same outlined "Meer laden" pill (styleguide, "Load more") under
  the queue, in both the phone/tablet bottom sheet and the desktop panel, shown only while the
  queue's feed has a next page. A tap calls `extendFeedQueue({ force: true })`, which fetches the
  next page at once, wherever the current track is. The automatic top-up near the end is
  unchanged. The native queue follows the `playlist` store, so the app gets the new tracks the same
  way.
- Tests: `feeds.test.js` (unresolved count, paging by MuMa's rows), `feedView.test.js` (the
  header note, a tapped row keeps the continuation, the button on the phone and the tablet with a
  98-track list), `feedQueue.test.js` (`force`), `queueFeedLoadMore.test.js`, and a Playwright
  check `tests/browser/feed-load-more.spec.js` (phone 412x915 and tablet 1280x800, touch) that
  scrolls to the pill, sees it in the viewport and loads the next page.

Left open (GitLab issue #98): whether the automatic top-up fires in the app while the phone is locked.
It runs in the WebView, and Android may suspend a backgrounded WebView's JavaScript. The native
side only continues a feed queue for Android Auto (`FeedQueueContinuation`, bug report 112).
