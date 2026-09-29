# Daily mixes with older tracks — Technical Design

Functional design: [functional.md](functional.md). Bug report
[131](../../bug-reports/131-daily-mixes-only-contain-this-year.md).

## Data Model

No schema change. Three runtime settings in `services/common/config_store.py`, group `Feeds`:

| Key | Type | Default | Range (else default) |
|---|---|---|---|
| `feeds_daily_recent_percent` | integer | 50 | 0–100 (the store has no float type) |
| `feeds_daily_recent_window_days` | integer | 365 | 7–3650 |
| `feeds_daily_older_min_rating` | integer | 3 | 1–5 |

`FeedPolicy` (`feeds/policy.py`) gains `recent_share` (None = no split), `recent_window_days`,
`older_min_rating`, `recent_pool_limit` (3000) and `older_pool_limit` (2000). `daily-mix`, the three
spectrum mixes and `daily-mix-label` carry a split and `release_window_days=None`; `release-radar`
and `daily-mix-artist` keep `recent_share=None` and their windows (7 and 90). The artist mix is left
alone on purpose: one artist's catalogue already spans the years (it measured 84 of 95 tracks older
than 2025 on the same day).

## Algorithm

Step 4 of `build_feed` for a split policy (`build._load_split_candidates`):

1. **Recent half** — `queries.split_sample_query(half='recent')`: the day-precision release date
   inside `[today - recent_window_days, today]` and the unheard-or-loved pool, as the mixes always had.
2. **Older half** — `split_sample_query(half='older')`: an agreed day-precision date before
   `today - recent_window_days`, and the song rating (the same roll-up as `heard`/`rating`: canonical,
   else best version, else own) at least `older_min_rating` or NULL. Profile-matched: primary artist
   in the top 50 profile artists, or a label in the top 50 labels, or a genre in the top 50 genres
   (uncorrelated `IN` subqueries); the label mix uses its label instead.
3. Each half is a sample of ids ordered by `MD5('<user>|<date>|<half>' || track_uid)` — stable for the
   day, like `daily_sample_key` — then fetched with `candidate_rows_query` in the candidate row shape
   plus a constant `pool` column, and collapsed to songs. A song in both halves stays recent only.
4. **Rediscovery**: for heard songs in the older half one bounded `last_listened_query` (per work or
   track) sets `rediscovery = scoring.rediscovery_factor(last)`: 0.2 when played today, rising linearly
   to 1.0 at 180 days; never heard is 1.0. It multiplies the daily draw's weight
   (`daily_sample_key`, which now floors only non-positive weights).
5. A hardness band filters both halves; there is no 90 → 365 → none ladder for a split policy.

Steps 6–7 (`build._select_split`): `round(size * recent_share)` places for the recent half and the rest
for the older half, each through the same `allocate`/`redistribute` over the genre shares. If the
older half cannot fill its places they go back to the recent half, and vice versa. The per-artist cap,
the unknown-hardness backfill and the song collapse are unchanged. `Feed.pool_counts` reports
`{'recent', 'older'}` of the emitted tracks.

Rotation (`daily-mix-label`): names are counted over one window, `None` (`SPLIT_ROTATION_WINDOWS`),
because the pool is the whole library; the artist mix keeps the 90/365/none ladder.

**Cost, measured read-only on production (2026-09-29, user user):** each sample is one scan of the
filtered library, ~9 s for the older half and ~8 s for the recent half; fetching 2000–3000 rows adds a
few seconds. The old 90-day query was one scan too. Builds run in the background refresh, so this
lands on `feeds-refresh`, not on Home; a continuation ("Meer laden") pays it live.

## API Contract

`GET /api/feeds/{slug}` gains `pool_counts` (`{"recent": n, "older": m}`, `null` for release-radar and
the artist mix). `GET /api/feeds` reports `window_days: null` for the split mixes (no window on the
pool). Additive; no client reads either field. `params_key` covers the three settings.

## Cross-App Impact

None: web and app render the returned list.

## Technical Acceptance Criteria

1. `test_feeds_build.RecentOlderSplitTest`: default 50/50, a 30 % share, fill in both directions, a
   song in both halves counted once, band filtering of both halves, the label mix's older half on its
   label, no older sample for radar and artist mix, rediscovery lookup only for heard songs.
2. `test_feeds_queries.SplitSampleQueryTest`: placeholder/param agreement, the older half's date and
   rating conditions, bounded seeded samples, profile match only in the older half.
3. `tests/integration/test_router_sql.py::FeedsPipelineTest::test_daily_mix_samples_older_songs_that_match_the_profile`
   runs both halves and the rediscovery lookup against MariaDB.
4. `test_feeds_router.ParamsKeyTest`: each of the three settings changes the key.

## Related Docs

- [docs/designs/feeds/](../feeds/) — the feeds algorithm this changes step 4 and 6–7 of.
- [docs/designs/feed-length/](../feed-length/) — continuation, which rebuilds with the same split.
