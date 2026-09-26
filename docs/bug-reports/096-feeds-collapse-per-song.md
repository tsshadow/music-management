# Feeds and song lists showed two versions of one song, and the rip instead of the official version

# status: fixed

# reported problem

Teun, 2026-09-26, production 0.75.1. The Release Radar listed Deadly Guns - KOPPEN ROLLEN twice:
track 9655173 (the YouTube file) and track 9652563 (the SoundCloud file), both in work 394638. And
for ERABREAK - Elevate, Thyron - Shatterproof, Yuuja - Energy Shield and Exoform - Colourless
Oppression the radar played the SoundCloud or YouTube rip (around 140 kbps) although the official
release sat in the library and was the canonical of its work. The same doubling was visible outside
the feeds: the phone home shelves "Recent uitgebracht" and "Recent toegevoegd", search, favourites,
shuffle and the genre lists. Teun's intent: everywhere except the song's own page, one entry per
song, and that entry is the best version -- the canonical.

# Possible reason

Song versions exist and mostly work (29,432 works with more than one version, 84,620 tracks), but
the surfaces never read them.

- **Feeds** (Release Radar, every daily mix and spectrum mix, on web, phone and Android Auto).
  `feeds/queries.py` `candidates_query` never selected `work_id`, so every file was its own
  candidate, and `feeds/build.py` only capped three per artist. The clients pass the feed's order
  through `getSongsByPath`, so what the feed emitted is exactly what played.
- **The rip beat the official version** because `heard` was per track: Teun had heard the official
  version, the rip counted as unheard, and `heard_rank_penalty` ranks unheard first. The official
  version then lost its place to its own rip.
- **Phone home shelves**: `PhoneHome.svelte` asked `getSpotifyTracks` without `deduplicate`.
- **LMS lists**: `search3` collapsed only client-side (`SearchResults.svelte`), and `getStarred2`,
  `getRandomSongs`, `getSongsByGenre` and `getSongsByFilter` (radio channels) not at all. The
  `canonicalOnly` filter existed, but only in `find_advanced`; `Track::find`'s query builder, which
  these endpoints use, ignored it.
- **Ratings**: once a list shows only the canonical, a favourite given to a rip would disappear
  from view. The song-versions design says ratings stay stored per version and display per song;
  that display roll-up was never built.

# solution

- **Feeds collapse to one candidate per work before ranking** (`feeds/build.py`
  `_collapse_to_songs`). The representative is the work's canonical; when the canonical is not a
  candidate itself (the rip is inside the release window, the official release is not) it is
  fetched in the same row shape (`canonical_rows_query`), so its path is what plays and it is
  scored on its own label and provenance. A canonical without a file leaves the qualifying version.
  The song's release date is the newest of the qualifying versions'. `heard` and `rating` are now
  per song in SQL: a listen of any version is a listen of the song, and the `unheard`/`loved` pools
  ask the same question. This applies to every policy because every policy loads through
  `_load_candidates`. The canonical choice itself and the grouping keys are unchanged.
- **Phone home shelves** send `deduplicate=true`.
- **LMS**: `Track::find` honours `canonicalOnly` and `workId` like `find_advanced`; `search3`
  (keyword searches only -- the empty query is a client's full-library sync and walks an id
  cursor), `getRandomSongs`, `getSongsByGenre` and `getSongsByFilter` set it. `getStarred2` maps
  each favourite to its canonical (`Track::findCanonicalVersion`) and lists each song once, at the
  place of its most recently rated version. Albums and playlists are left as they are: they are an
  explicit context the release or the user chose, and a playlist that silently swapped a file the
  user put there would be a different bug. The song page (`workId=`) still lists every version. An
  index on `track(work_id)` backs the per-row lookups.
- **Rating roll-up** (`IFeedbackService::getSongRating`, used by every song node): the canonical of
  a work shows its own rating when it has one, else the highest this user gave any other version,
  and is a favourite accordingly. Deviation from the design's "highest in the group": a rating given
  from a list is written to the canonical, so under a plain maximum lowering a song's rating from a
  list could never show. For the same reason clearing the canonical's rating (unstar, rating 0)
  clears it on every version, or a favourite unstarred from the favourites list would stay there.
  Non-canonical versions (only on the song page) show their own rating. The feeds use the same rule.
- Tests: `test_feeds_build.py` `CollapseToSongsTest`, `test_feeds_queries.py`,
  `tests/integration/test_feed_song_collapse.py` (MariaDB), `phoneHome.test.js`, and the LMS GTests
  `database/test/SongVersions.cpp` and `FeedbackService.theCanonicalShowsTheSongRating...`.

Known limit: search3 now lists a song only through its canonical, so a keyword that matches only a
non-canonical version's own title (a word like "extended" that the canonical lacks) no longer finds
it; the base title, artist and label still do, and the song page lists every version.
