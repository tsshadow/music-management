# Listening Statistics — Technical Design

Functional counterpart: [functional.md](functional.md).

## Where this lives

A new router, `services/music_manager/routers/listening.py`, mounted at `/api/listening`.

It deliberately does **not** extend `/api/analytics`. That router's shared machinery
(`analytics_filters.py`) starts from one row per library *track*: `FROM_CLAUSE` joins artists and
audio features one-to-one so `SUM()` stays meaningful, and its `year_min`/`year_max` are a track's
*release* year. Every question here starts from one row per listening *event* and its year is the
year it was played. Reusing that base would silently select the wrong population and could not reach
the unmatched table at all. The two routers also both want `/summary`, `/top-artists` and
`/top-labels`, which is a second reason to keep the prefixes apart.

## Data model

No new tables. Two existing ones, both bootstrapped in `routers/scrobbler.py` rather than
`services/common/db_init.py`:

- `scrobble_listens` — `track_id`, `listened_at`, `username`, `source`, `match_method`,
  `match_score`, `played_secs`. `track_id` is nullable.
- `scrobble_unmatched_listens` — `artist_name`, `track_title`, `album_name`, `listened_at`,
  `username`, `source`, `attempts`, `last_attempt_at`, `played_secs`.

`library_tracks.duration_secs` is a nullable `FLOAT`, so an imputed duration can be absent and every
sum over it is rounded before it leaves the API.

### Indexes

Both tables carry a unique key leading on `username`, which serves "my listens between two dates".
Neither has an index leading on `listened_at`, which is what "everybody's listens between two dates"
needs. `migrate_v20_listening_indexes.sql` adds one to each, mirrored by two `ADD INDEX IF NOT
EXISTS` statements in `scrobbler.py`'s `init_db` so a fresh stack gets them too.

No `track_id` index is added: `scrobble_listens` already has one from the rematch migration, and a
date-filtered `GROUP BY track_id` cannot use a filtering and a grouping index at once.

## Endpoints

All are GET, all authenticate with `X-API-Key`, all accept `from`, `to`, `tz` and `username`.

| Path | Population | Returns |
|---|---|---|
| `/summary` | both | counts, duration breakdown, first/last listen |
| `/timeline?bucket=day\|week\|month` | both | listens per bucket, matched and unmatched split |
| `/clock` | both | 24 hour counts and 7 weekday counts |
| `/sources` | both | listens per `source`, NULL as `unknown` |
| `/top-tracks?limit=` | linked only | track, artist, listens, estimated seconds, last listen |
| `/top-artists?limit=` | linked only | primary artist, listens, distinct tracks, estimated seconds |
| `/top-labels?limit=` | linked only | label, listens, distinct tracks |

Every ranking also returns the unmatched count for its scope, so the page never has to make a second
call to render its own caveat.

## Scope and authorisation

`parse_scope` is one dependency shared by all seven endpoints.

| Credential | No `username` | Explicit `username` |
|---|---|---|
| System key | every user | that user |
| User key | own username | own username, or **403** if it names anyone else |

Rejecting rather than ignoring differs slightly from `routers/feeds.py`, which silently pins a user
key to its own name. Rejecting is the same guarantee and says so out loud. This matters because the
LMS proxy (`MumaResource.cpp`) forwards the query string and the caller's key untouched and enforces
nothing itself: without this check, one listener's key would read every listener's history.

## Duration

`played_secs` is present on 876 of 20.299 linked listens on production. Reporting one "listening
time" from a `COALESCE` over that would present a 96% assumption as a measurement, so `/summary`
returns the parts:

| Field | Meaning |
|---|---|
| `measured_secs` | `SUM(played_secs)`, over both tables. A reported `0` is measured. |
| `imputed_secs` | `library_tracks.duration_secs` where `played_secs IS NULL`, linked listens only |
| `estimated_secs` | the two added |
| `measured_listens` / `imputed_listens` / `unknown_duration_listens` | which listens fell where |
| `measured_share` | `measured_listens / listens`, **null** on an empty scope |

An unmatched listen with no `played_secs` has no track to borrow a duration from, so it lands in
`unknown_duration_listens` and contributes nothing. `estimated_secs` is therefore a floor, not a
guess at the whole. The page labels it an estimate and prints `measured_share` beside it.

## Timezone

`listened_at` is a `TIMESTAMP` and production's database container runs on UTC — `NOW()` equals
`UTC_TIMESTAMP()`. `HOUR()` therefore reports a UTC hour, which is two hours off in Amsterdam in
summer and one in winter. A single browser offset would fix one season and break the other.

The caller sends an IANA zone name instead (`tz=Europe/Amsterdam`, default `UTC`), validated with
`zoneinfo`; an unknown zone is a 400. `CONVERT_TZ` is not used — it needs the MySQL timezone tables,
which are not loaded on this server.

- **Range boundaries** are converted once in `ListeningScope._as_utc`: a local midnight becomes the
  UTC instant the WHERE clause compares against. `to` is exclusive on the *next* local midnight, so
  the last day of a range is whole.
- **Buckets** are not computed in SQL. `_hourly()` asks for one row per UTC hour that saw a listen —
  a few thousand rows over three years, not 54.000 — and converts each to the caller's zone in
  Python, where DST is handled. `/timeline` and `/clock` both read that one rollup.
- A whole UTC hour is assumed to fall inside one local hour. True for every whole-hour offset; off
  by one bucket for the handful of zones at :30 or :45.

## SQL notes

- The WHERE fragment uses **unqualified** `username` and `listened_at`. Both columns exist only on
  the two listens tables and on none of the library tables joined beside them, so no alias is needed
  and the fragment stays a constant string rather than one built per call.
- `/top-labels` joins `library_track_labels`, whose primary key is `(track_id, label_id)`. Grouping
  by label id therefore counts each listen once *within* each label. A track with two labels counts
  for both, so the column does not sum to the total — which is why no share is returned there.
- `/summary` runs two queries rather than one join: the tables have no relation to join on.

## Frontend

- `src/lib/listeningStats.js` — URL building, period ranges, bucket choice, the disclosure
  arithmetic. Kept out of the component so the parts that can be wrong are testable without
  rendering.
- `src/lib/ListeningStatsView.svelte` — the page. Bars are divs, as in `AnalyticsPanel.svelte`;
  there is no charting dependency in `package.json` and this does not add one. Every value that a
  tooltip shows is also in the DOM as text.
- Route `listening` in `router.js` `PLAIN_VIEWS`, dispatched in `Dashboard.svelte`, listed in
  `Sidebar.svelte`'s `tailItems` next to History and Memories.
- The period selector offers 30 days, 12 months and all time, bucketed day / week / month. Three
  years of daily bars is about a thousand of them and reads as noise, so only the shortest period
  gets days.
- `Promise.all` over seven endpoints, each resolving to `null` on failure: one dead panel does not
  blank the page.

## Cross-app impact

None. Nothing on the Subsonic surface changes, the mobile app is untouched, and the scrobble write
path is unchanged apart from two `ADD INDEX IF NOT EXISTS` statements in `init_db`.

## Acceptance Criteria

1. `GET /api/listening/summary` totals both tables; `matched + unmatched == listens`.
2. `measured_secs`, `imputed_secs` and `estimated_secs` are separate fields, and
   `estimated_secs == measured_secs + imputed_secs`.
3. `measured_share` and `unmatched_share` are `null`, not `0`, when the scope holds no listens.
4. `unknown_duration_listens` accounts for every listen that is neither measured nor imputed.
5. `timeline` with an unknown bucket answers 400; `clock` with an unknown zone answers 400; a range
   whose `to` precedes its `from` answers 400.
6. A 23:00 UTC listen in January and one in July fall in different local hours for
   `tz=Europe/Amsterdam`.
7. `from=2026-01-01&tz=Europe/Amsterdam` binds `listened_at >= 2025-12-31 23:00` in UTC.
8. Every ranking returns the unmatched count for its scope.
9. A user key naming another username gets 403; naming none is scoped to its own; a system key
   naming none is unscoped.
10. Every new GET endpoint appears in `tests/integration/test_router_sql.py`, and
    `listening` is registered in that suite's `conftest.py` connection patch list.
11. `init_db` creates both `listened_at` indexes on a database that predates them.
