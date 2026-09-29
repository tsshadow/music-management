# Daily Mixes Only Contain This Year's Tracks

# status: fixed

# reported problem
Teun, 2026-09-29: "The daily mixes seem to contain only this year. I also want some older tracks,
otherwise I might as well just pick 'uptempo this year'."

Measured read-only on production (`feeds_snapshot`, user user, feed_date 2026-09-29), release year
per mix of 100:

| mix | 2026 | 2025 | older |
|---|---|---|---|
| daily-mix (Klassiek) | 100 | 0 | 0 |
| daily-mix-soft | 99 | 0 | 1 |
| daily-mix-mid | 96 | 1 | 3 |
| daily-mix-hard | 98 | 0 | 2 |
| daily-mix-label (37 tracks) | 25 | 12 | 0 |
| daily-mix-artist | 4 | 7 | 84 |

# Possible reason
By design, not a defect in the code: every daily mix shared `_DAILY_MIX_BASE` in
`services/music_manager/feeds/policy.py`, with `release_window_days=90`, so the candidate query only
ever saw releases of the last 90 days (`queries._release_window_conditions`). On 2026-09-29 that
reaches back to 2026-07-01, hence "this year". The newest-release-first sort key in `build.py`
(`_release_sort_key`) is only used by Release Radar's `order='release'`; the daily mixes use the
day-stable weighted draw, so the ordering pushed nothing out -- the window alone did.

The spectrum mixes widen the window only when a band has fewer than 15 candidates, which on this
library never happens. The artist mix was the exception because one artist rarely has 15 unheard
songs in 90 days, so its window widened to all time -- which is why it was the one mix with older
tracks.

# solution
The daily mixes -- Klassiek, Zachter/Middenin/Harder and the label mix -- split their places:
by default 50 % from songs released within the last 365 days (the unheard-or-loved pool as before)
and 50 % from songs released before that, restricted to songs rated 3 stars or more or not rated at
all, profile-matched on the listener's top artists, labels and genres, and weighted towards songs
not played in the last 180 days. Either half short fills from the other, so the length holds.
Release Radar and the artist mix are unchanged. The share, the window and the minimum rating are
settings (`feeds_daily_recent_percent`, `feeds_daily_recent_window_days`,
`feeds_daily_older_min_rating`) and part of the snapshot key. Design:
`docs/designs/daily-mix-older-tracks/`.

Expected for user on 2026-09-29, from a read-only run of the new sample queries: of 100 places about
35 from 2026 and 15 from late 2025 (the recent pool is 31 % 2025 / 69 % 2026), and 50 older ones
spread over the years the way the profile-matched sample is -- 10 % 2025 (before 29 September),
14 % 2024, 11 % 2023, 28 % 2020-2022, 25 % 2016-2019, 12 % 2015 and earlier.
