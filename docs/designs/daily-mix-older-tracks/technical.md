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

**Cost** (issue #137, measured read-only on production 2026-09-29, user user, server-side time via
`SYSDATE(6)` around the statement):

| Statement | Before | After |
|---|---|---|
| recent-half sample (3000 ids) | 4.84 s | 1.65 s |
| older-half sample (2000 ids) | 6.05 s | 2.69 s |
| Release Radar candidate query | 1.50 s | 1.31 s |
| candidate rows by id (~1900 rows, PK range) | 0.13 s | 0.11 s |
| "Meer laden" on a split mix | a full build (two samples, ~11 s of SQL) | no build: read + write-back of the row |

**Shared samples** (issue #138, measured read-only on production 2026-09-30, user user, same
`SYSDATE(6)` method, two runs each): Klassiek, Zachter, Middenin and Harder ask the very same two
sample questions -- same user, day, split settings and profile match; the hardness band is applied
afterwards in Python -- so `build._sample_ids` memoises the ids of each sample in-process for
`SAMPLE_MEMO_TTL_SECONDS` (600 s), keyed on the rendered statement and its parameters. Whatever can
change the answer (user, day, settings, the older half's profile names, the label mix's filter) is in
the key by construction; the label mix therefore keeps its own pair. Only the ids are kept, in their
`MD5(seed || track_uid)` order, so a build that reuses them fetches, scores and orders exactly what it
would have fetched itself (`SharedSampleTest` builds all four with and without sharing and compares
the whole `Feed`). At most `SAMPLE_MEMO_MAX_ENTRIES` (32) samples are held, ~110 kB for a full
recent one.

| Per listener, per day (feeds-refresh) | Before | After |
|---|---|---|
| recent-half sample (3000 ids) | 4 × 1.99 s | 1 × 1.99 s |
| older-half sample (2000 ids) | 4 × 4.13 s | 1 × 4.13 s |
| sample SQL for the four hardness-family mixes | ~24.5 s | ~6.1 s |

The memo also covers on-demand builds: after a settings change each mix is rebuilt on its own
request, on its own connection, and the second to fourth of those within ten minutes reuse the
first one's samples. A rebuild later than that samples again, so a newly scanned track or a new
rating is never kept out of a mix for longer than the TTL.

The cost was not the scan itself but the audio-features derived table joined into every statement:
`EXPLAIN` shows it as `LATERAL DERIVED` -- a `GROUP BY` over `idx_af_internal_track_id` for each of
the ~345k scanned rows, only to supply a release date that `library_tracks.release_date` already
settles for all but 377 of them. Every read of `library_track_audio_features` in `feeds/queries.py`
is now a correlated aggregate lookup (`_AF_BPM`, `_AF_RELEASE_YEAR`, `_AF_RELEASE_DATE`), and
`_RELEASE_DATE` only evaluates its lookup when the track's own date is NULL. Same rows, same values:
the before/after statements returned identical aggregates. The samples keep their day-stable
`MD5(seed || track_uid)` order, so a day's mix is unchanged by the rewrite.

The continuation no longer samples at all: the head build also ranks `MAX_FEED_LENGTH` places and
stores the rest as `reserve` (see docs/designs/feed-length/technical.md, "Continuation").

## API Contract

`GET /api/feeds/{slug}` gains `pool_counts` (`{"recent": n, "older": m}`, `null` for release-radar and
the artist mix). `GET /api/feeds` reports `window_days: null` for the split mixes (no window on the
pool). Additive; no client reads either field. `params_key` covers the three settings. The stored
row of a split mix also carries `reserve` (issue #137), which `get_feed` strips like `exhausted`.

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
