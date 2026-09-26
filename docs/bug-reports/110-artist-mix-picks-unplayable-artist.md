# The daily artist mix picks an artist with no playable tracks

# status: fixed

# reported problem

GitLab issue #77. On 2026-09-26 a live `daily-mix-artist` build for Teun picked the artist
"unproven" and returned 0 candidates. The snapshot served that same day (built at 00:01 local
time) had picked "valhalla" and held only 2 tracks (`funnel` 2/2/2/2/2). The label mix served
that day, "snakepit music", held 3.

# Possible reason

The first suspicion was the fileless first-scan stubs purged that evening (bug report 104): the
old "unproven" tracks were such stubs. Re-measured on production after the purge (~32,700 orphans
removed, ~48,900 relinked), that is not it. Unproven now has 400 tracks, 399 of them with a file,
350 within the duration bounds, 165 songs -- and today's draw is still unproven
(`md5('user|2026-09-26|entity') % 10` = index 4 of the top ten), and it still gets 0 candidates.

The real cause is that `pick_daily_entity` drew a name from the top ten without ever asking whether
it could fill a mix, while three filters stacked on a single artist leave almost nothing:

- the 90-day release window every daily mix shares: only 8 of unproven's playable tracks fall in
  it, and all 8 are heard and none rated 4 or higher, so the unheard-or-loved pool removes every one;
- the rotating mixes never got the band mixes' relaxation ladder (90 -> 365 -> no window);
- the per-artist cap of 3 applies to the artist mix too, where every candidate has the same primary
  artist, so even an artist with 30 candidates could never be served more than 3 tracks.

Measured on production for Teun's top ten artists (songs, after the pool, per window):

| artist | 90 days | 365 days | no window |
|---|---|---|---|
| drs | 0 | 13 | 245 |
| deadly guns | 3 | 9 | 161 |
| samynator | 5 | 7 | 20 |
| lekkerfaces | 5 | 8 | 80 |
| unproven | 0 | 4 | 119 |
| dual damage | 5 | 24 | 77 |
| sickmode | 7 | 18 | 142 |
| pinotello | 3 | 8 | 41 |
| valhalla | 2 | 10 | 18 |
| dimma | 0 | 1 | 5 |

No artist reaches 15 songs at 90 days, so no rotation of that policy could ever have produced a
real mix. Valhalla's 2 is exactly the snapshot's 2.

# solution

`build._describe` now counts before it draws, with one grouped query over the whole top ten
(`queries.rotation_counts_query`): the candidate filters (a media file, the duration bounds, the
unheard-or-loved pool), counted per song (`COALESCE(work_id, -id)`, the key the song collapse
uses) once per window of the ladder 90 / 365 / no window. No candidate query per name tried.

`scoring.pick_playable_entity` starts at the same day-stable index and walks the ranking, wrapping
around, taking the first name with at least `MIN_ROTATION_CANDIDATES` (15, the same floor as
`MIN_BAND_CANDIDATES`: half of the 30 places) songs at the narrowest window that has them. The drawn
name at a wider window beats the next name at 90 days. The build then queries candidates at that
window and reports it as `relaxed_to`. When no name in the top ten qualifies the mix reports
`no_matches` with no tracks and the default title, never an `ok` mix of two tracks.

`daily-mix-artist` no longer applies the cap of 3 per artist (`max_per_artist` = the mix size); the
label mix keeps it.

With this, Teun's artist mix for 2026-09-26 is unproven at no window (119 songs, 30 places), and the
label mix is masters of hardcore at 365 days (16 songs).

Tests: `test_feeds_scoring.PickPlayableEntityTest`, `test_feeds_build.RotatingMixPlayableArtistTest`,
`test_feeds_queries.RotationCountsQueryTest`, and two integration tests in
`tests/integration/test_router_sql.py` (`FeedsPipelineTest`) running the count query on MariaDB.
