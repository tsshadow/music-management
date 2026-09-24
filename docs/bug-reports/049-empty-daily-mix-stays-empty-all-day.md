# An Empty Daily Mix Stays Empty For The Rest Of The Day

# status: fixed — a non-ok snapshot lives 15 minutes, the key covers hardness and exclusions, the day is local

# reported problem
Found reading the feeds snapshot code (`feeds/snapshot.py`, `feeds/build.py`, `routers/feeds.py`)
after the home-load work, not reported by a listener. Three ways a daily mix shows the wrong thing
for the rest of a day:

- A listener who opens Home before their first listen, on a server where nobody has listened yet,
  gets `not_enough_data` for every mix. The rotating artist and label mixes do the same for any
  profile without artist or label affinities, and a spectrum mix whose band is empty says
  `no_matches`. That answer was stored as the day's snapshot, and a daily-mix row is fresh all day
  whatever it contains: after the first listens the mixes stayed empty until midnight.
- A curator who re-scores a genre's hardness (`PUT /api/curation/genres/{name}/hardness`) moves
  tracks between the Zachter/Middenin/Harder mixes, but the snapshots were keyed on the settings
  only, so the edit reached the mixes the next day.
- The day itself was the container's: `music-manager` has no `TZ` and runs on UTC, so the mixes
  rolled over at 01:00 (winter) or 02:00 (summer) Amsterdam time. A mix built at 00:30 used
  yesterday's draw and was then kept as today's.

# Possible reason
- `snapshot.is_fresh` looked at the slug and the settings key only; `state` was never consulted.
- `refresh_stale` only rebuilds rows `is_fresh` calls stale, so the background pass did not help
  either: the new listener's empty rows were "fresh".
- `routers/feeds.py`'s `params_key` digested the starting genres and the hardness edges, not the
  per-genre `rules_genres.hardness` values the spectrum bands are built from, and not the
  listener's exclusions. An exclusion change deleted the listener's rows, but a build already
  running on the old exclusions wrote its row afterwards, under a key that still matched.
- `serve` and `refresh_stale` took `feed_date` from `now.date()`, and `build_feed` seeded the daily
  draw and the artist/label rotation with the same UTC date.

# solution
- A row whose payload `state` is not `ok` is fresh for `FEEDS_NON_OK_TTL_SECONDS` (default 900)
  only, then rebuilt on the next read. The refresh pass rebuilds it too once the listener has a
  listen, so their mixes fill in the same day.
- `params_key(conn, username, slug)` also digests the listener's exclusions (every slug) and an
  aggregate checksum over `rules_genres.hardness` (the three spectrum mixes and the listing). It is
  computed before the build, so an exclusion or hardness edit that lands mid-build leaves the row
  that build writes stale.
- `feeds/clock.py`'s `feed_date` reads the calendar day in `MUMA_TIMEZONE` (default
  `Europe/Amsterdam`); the snapshot, the daily sample order and the rotation all use it.
- Tests: `test_feeds_snapshot.py` (`FreshnessTest`, `FeedDateTest`, the refresh pass for a
  listener whose mix was empty) and `test_feeds_router.py` (`ParamsKeyTest`).
