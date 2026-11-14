# MuMa Wrapped Page — Technical Design

Implements [functional.md](functional.md). The data groundwork is in
[../wrapped/technical.md](../wrapped/technical.md). The listening queries reuse the scope, time
zone and disclosure rules of [../listening-stats/technical.md](../listening-stats/technical.md).

"OQ n" names decision n in functional.md. Every decision was taken on 2026-11-12, as recommended.

## Where this lives

- Backend: a router `services/music_manager/routers/wrapped.py`, mounted at `/api/wrapped`, and a
  package `services/music_manager/wrapped/`:
  - `data.py` reads a period once: every listen of both tables in `{W}`, and the genres, labels,
    channels, tempo and remixers of the tracks they found, about ten queries.
  - `listening_cards.py` holds the listening cards as pure functions of that data,
    `card_<id>(data, ...) -> dict`, so a card test needs no cursor.
  - `collection_cards.py` holds the Library cards that read the collection, with their own SQL.
  - `payload.py` sets the card order per tab and adds `file_path` and `library_path` (the path without the library root) to every track a card
    names.
  - `periods.py` parses `year` / `from` / `to` / `tz`, `snapshots.py` stores a tab, `cards.py`
    builds the status fields, and `words.py` holds the stop list.
- It imports `ListeningScope`, `parse_scope`'s rules, `release_year_sql` and the duration split from
  `routers/listening.py`. It does not call those endpoints over HTTP.
- Frontend: `src/lib/wrapped/` with `wrapped.js` (URL, period and payload logic, tested without
  rendering), `WrappedView.svelte` (tabs, period picker, card run), one component per card kind
  (`HeroCard`, `RankCard`, `BarsCard`, `ClockCard`, `HeatmapCard`, `FactCard`, `CoverageCard`) and
  `shareCard.js` (canvas export).
- The Android app shows the same bundle. The only app change is a `share` call on `MumaSystemPlugin`
  (OQ 5).

## Definitions shared by every card

| Term | Definition |
|---|---|
| Period `P` | `[from, to]` local dates in zone `Z`, converted to a UTC half-open interval by `ListeningScope._as_utc`. A year `Y` is `Y-01-01 .. Y-12-31`. A running period ends today. |
| `Z` | User tab: the `tz` parameter (IANA name, default `UTC`, OQ 8). Library tab: config key `wrapped_server_tz`, default `Europe/Amsterdam`. |
| Scope | User tab: `username = <caller>`, pinned as in `parse_scope` (a user key naming someone else is 403). Library tab: no username filter, so every account, including `deleted-<id>` tombstones (#220). |
| `{W}` | `ListeningScope.where()`: username and `listened_at` in `P`. Valid on both listens tables. |
| Linked listen | A `scrobble_listens` row in `{W}` with `track_id IS NOT NULL`. |
| All listens | Linked listens plus `scrobble_unmatched_listens` rows in `{W}` (OQ 1). |
| Local time of a listen | `listened_at` (UTC) converted to `Z` in Python, from the hourly rollup `_hourly()`, or per row where a card needs exact order. |
| Real label | A `library_labels` row. Since the channels work (Part 2 of the groundwork) no acquisition source or placeholder is a label. A track's labels are `library_track_labels` plus `channels.label_id` of its channels. |
| Effective BPM | `library_track_effective_bpm.bpm` where `confidence <> 'low'`. |
| Release year | `release_year_sql('t')` from `listening.py`. |
| Unmatched disclosure | Every linked-only card returns `unmatched`, the count of unmatched listens in `{W}`. |

A card returns:

```jsonc
{
  "id": "top_tracks",
  "status": "ok" | "empty" | "below_minimum" | "blocked",
  "reason": "no_arrival_date",      // only for blocked and below_minimum
  "basis": {"counted": 4120, "of": 5044, "unit": "listens"}, // what the card is based on
  "data": { /* card specific, below */ }
}
```

`empty` means no rows. `below_minimum` means rows exist but fewer than the card's minimum.
`blocked` means the source data does not exist (arrival date, remixer). The frontend renders `ok`
only and passes the rest to the coverage card.

## Cards and their SQL

SQL is written for `scrobble_listens l`, `library_tracks t`. `%(from)s`, `%(to)s` are the UTC bounds
and `{W}` the fragment above. Rankings break ties on name, then id, so two requests give the same
order. "Min" is the minimum for status `ok`.

### Listening cards (both tabs unless marked)

| Card id | Data | Source and definition | Min |
|---|---|---|---|
| `title` | listens, linked, unmatched, distinct_tracks, estimated_secs | `summary()` logic from `listening.py`: `COUNT(*)` on both tables in `{W}`, `COUNT(DISTINCT track_id)` on linked | 1 listen |
| `listening_time` | measured_secs, imputed_secs, estimated_secs, measured_share | Same duration split as `/api/listening/summary` | 1 listen |
| `listeners` (Library) | active, former | `SELECT username LIKE 'deleted-%%' AS former, COUNT(DISTINCT username) FROM (SELECT username FROM scrobble_listens WHERE {W} UNION SELECT username FROM scrobble_unmatched_listens WHERE {W}) u GROUP BY former` | 1 |
| `top_tracks` | 5 of track_id, title, artist, listens, file_path | `SELECT t.id, t.title, t.display_artist, COUNT(*) n FROM scrobble_listens l JOIN library_tracks t ON t.id=l.track_id WHERE {W} GROUP BY t.id ORDER BY n DESC, t.title LIMIT 5`, plus the first `library_media_files.file_path` per track for playback | 3 tracks |
| `top_artists` | 5 of artist_id, name, listens, image | `JOIN library_track_artists ta ON ta.track_id=t.id AND ta.role='primary' JOIN library_artists a ON a.id=ta.artist_id ... GROUP BY a.id` | 3 artists |
| `top_genres` | 5 of genre, listens, tint | `/api/listening/top-genres` query (excludes `state='black'`), plus `untagged` | 3 genres |
| `seasons` | per season: genre, listens | Same join, grouped by season of the local date (Dec-Feb winter, Mar-May spring, Jun-Aug summer, Sep-Nov autumn); top genre per season | 2 seasons with 20 listens |
| `top_label` | label, listens, tracks, runner-up 4 | Listens per real label: `SELECT lb.id, lb.name, COUNT(DISTINCT l.id) n FROM scrobble_listens l JOIN (SELECT track_id, label_id FROM library_track_labels UNION SELECT tc.track_id, c.label_id FROM library_track_channels tc JOIN channels c ON c.id=tc.channel_id WHERE c.label_id IS NOT NULL) x ON x.track_id=l.track_id JOIN library_labels lb ON lb.id=x.label_id WHERE {W} GROUP BY lb.id ORDER BY n DESC LIMIT 5` | 10 listens |
| `top_channel` | platform, channel, listens, linked label/artist | `JOIN library_track_channels tc ON tc.track_id=l.track_id JOIN channels c ON c.id=tc.channel_id ... GROUP BY c.id` | 10 listens |
| `top_remixer` | remixer, listens | `role='remixer'` on `library_track_artists`. Production holds 0 such rows: status `blocked`, reason `no_remixer_credits` until OQ 12 is built | 5 listens |
| `festival` | festival, listens, hours, editions played | Linked listens whose `t.form IN ('set','liveset')`, festival found in Python with `FestivalHelper.get_all(title)` (then path with a year), the same matcher `track_form.py` uses. Hours: `SUM(COALESCE(played_secs, t.duration_secs))`, marked estimate when any `played_secs` is NULL | 2 listens |
| `time_travel` | oldest and newest edition: festival, year | Same rows, edition year from `t.performance_date`, else the year `FestivalHelper` found in the title | 2 editions |
| `show` | show, listens, hours | Linked listens with `t.form='podcast'`, show matched with the podcast lookup `derive_form` uses (approved `rules_podcasts` names and aliases) | 2 listens |
| `forms` | per form: listens, measured_secs, estimated_secs | `GROUP BY t.form` on linked listens; `interview` and `preview` fold into "other"; NULL form is "unknown" | 10 listens |
| `bpm` | average, per month average, counted | `JOIN library_track_effective_bpm b ON b.track_id=l.track_id AND b.confidence<>'low'`; average per listen, not per track; month of the local date | 20 listens with a BPM |
| `bpm_extremes` | fastest and slowest track, bpm | Same join, `ORDER BY b.bpm DESC/ASC LIMIT 1`, only `confidence='high'` so a misfolded value does not win | 20 |
| `taste_vs_shelf` | two 5-BPM histograms, both as shares | Listens: `GROUP BY FLOOR(b.bpm/5)*5` on the join above. Shelf: same over all of `library_track_effective_bpm` (cached per day, it is the same for everyone) | 50 |
| `clock` | 24 hours, 7 weekdays | `_hourly()` rollup over all listens, converted to `Z` | 20 |
| `heatmap` (Library) | 7 x 24 matrix | Same rollup, weekday x hour | 50 |
| `night_shift` | share 00:00-04:59 | From the rollup | 20 |
| `busiest_day` | date, listens | Rollup summed per local date, maximum | 5 |
| `first_last` | first and last listen: time, title, artist | `ORDER BY listened_at ASC/DESC LIMIT 1` on both tables, the earlier/later wins; unmatched listens use their raw text | 1 |
| `months` | listens per month, linked and unmatched | `/api/listening/timeline?bucket=month` logic | 1 |
| `streak` | days, first day, last day | Distinct local dates from the rollup; longest run of consecutive dates, in Python | 2 days |
| `session` | start, end, listens, duration | All listens of `P` ordered by `listened_at` (50.000 rows a year at most, read in one query): a session continues while `next.listened_at - prev.listened_at <= COALESCE(prev.played_secs, prev duration, 0) + 900 s`. Duration is last minus first plus the last listen's length | 3 listens |
| `origins` | per origin: listens, measured_secs; car hours | `GROUP BY source`, mapped: `frontend` web, `mobile` phone, `auto` car, `lms-web` legacy web, `listenbrainz*` and `lms-history-import*` imported, everything else (incl. `lms`, `manual`) unknown. Car hours `SUM(played_secs) WHERE source='auto'` | 10 |
| `release_years` | oldest and newest release year played (with track), plays per decade, unknown | `/api/listening/years` query, decades folded in Python | 10 with a year |
| `fresh_vs_stock`, `long_wait`, `impulse` | share of plays of tracks arrived in `P`; longest arrival-to-first-play; median of it | Need `library_tracks.arrived_at` (OQ 3, below). Without it: `blocked`, reason `no_arrival_date` | 10 |
| `untouched` | played distinct tracks, library size, share | `COUNT(DISTINCT l.track_id)` linked over `{W}` and `SELECT COUNT(*) FROM library_tracks WHERE form IS NULL OR form NOT IN ('interview','preview')` | 1 |
| `new_genres` (User) | genres first played in `P` | Genres of linked listens in `P` minus genres of this user's linked listens before `from`: `... WHERE {W} AND g.id NOT IN (SELECT tg2.genre_id FROM scrobble_listens l2 JOIN library_track_genres tg2 ON tg2.track_id=l2.track_id WHERE l2.username=%s AND l2.listened_at < %(from)s)` | 1 |
| `discovery` (User) | artist, listens in `P`, first listen | Primary artists whose first listen by this user (all time) is in `P`, ranked by listens in `P` | 3 listens |
| `loyal` (User) | artist, months | `COUNT(DISTINCT local month)` per primary artist, top 1, ties by listens; shown only when it differs from `top_artists[0]` | 3 months |
| `one_hit` (User) | artist, date, listens | Primary artists with all their listens in `P` on one local date and at least 5 of them; most listens wins | 5 listens |
| `ratings` (User) | given, per star, five_star_play_share | `rating_tracks WHERE username=%s AND entity_type='track' AND updated_at` in `P`; play share: linked listens whose `t.track_uid` has a 5 by this user, over linked listens. Basis note when `P` starts before 2026-07-04 (rebuild) | 5 ratings |
| `contradiction` (User) | track, rating, listens | Linked listens in `P` joined to `rating_tracks` on `entity_id = t.track_uid AND username = l.username AND rating <= 2`, top by listens | 3 listens |
| `word` | word, count, runner-ups | Titles of all listens (`t.title`, `u.track_title`), lowercased, split on non-letters, words of 3+ letters, minus a stop list in `wrapped/words.py` (`the`, `and`, `feat`, `ft`, `vs`, `with`, `you`, `for`, `het`, `een`, `van`, `original`, `mix`, `version`); counted per listen | 20 listens |
| `unidentified` | listens, distinct | All listens whose title matches `^\s*id\s*$` or artist and title are both `ID` (case-insensitive) | 1 |
| `only_you` (User) | track only you played, shared_tracks | Most played linked track in `P` with `NOT EXISTS (SELECT 1 FROM scrobble_listens o WHERE o.track_id=l.track_id AND o.username<>l.username AND o.listened_at` in `P`)`; and the count of your distinct tracks that someone else also played. Counts only, never a name (OQ 7) | 3 tracks |
| `most_shared` (Library) | track, listeners | `COUNT(DISTINCT username)` per linked track, top 1, at least 2 listeners | 2 listeners |

### Collection cards (Library tab)

| Card id | Data | Source and definition | Min |
|---|---|---|---|
| `releases_of_year` | tracks released in `P`'s year(s), top 5 labels | `SELECT COUNT(*) FROM library_tracks t WHERE LEFT(t.release_date,4) BETWEEN %s AND %s`, labels through the real-label union above. 27.020 tracks for 2026 on 2026-11-12. For a custom range: release dates inside the range, day precision only | 1 |
| `downloads` | per month and platform; top channel | `downloads_soundcloud_archive.added_at` and `downloads_youtube_archive.added_at` in `P`, `GROUP BY` local month; top `account` by rows. Rows with a NULL `added_at` are counted in `basis` as undated | 1 |
| `growth` | tracks arrived in `P` by source | `library_tracks.arrived_at` in `P`, `GROUP BY arrived_source` (OQ 3). Without it: `blocked` | 1 |
| `festival_editions` | editions in the collection with a performance date in `P` | `SELECT COUNT(*) FROM library_tracks WHERE form='liveset' AND performance_date BETWEEN %s AND %s`, festival names by `FestivalHelper` over those titles | 1 |
| `shelf` | BPM histogram, genre spread top 10, coverage | `library_track_effective_bpm` histogram (above) and `library_track_genres` counts per non-black genre | 1 |
| `start_now` | total_secs, finish date | `SUM(duration_secs)` over `library_tracks` (316.103.088 s on 2026-11-12); finish date = generation time + total | 1 |
| `unplayed` | tracks nobody played in `P`, share | Library size minus `COUNT(DISTINCT track_id)` of all accounts' linked listens in `P` | 1 |
| `system` | bpm_measured, bulletins, ratings, criticals | `library_track_bpm WHERE status='ok' AND analyzed_at` in `P`; `news_bulletins WHERE created_at` in `P`; `rating_tracks WHERE updated_at` in `P` (all users); `events WHERE level='CRITICAL' AND created_at` in `P`. Lower levels expire before a year ends, so they are not shown | 1 |

### The arrival date (OQ 3, recommended option a)

| Column on `library_tracks` | Type | Meaning |
|---|---|---|
| `arrived_at` | `DATETIME NULL` | When the file first entered the library, or NULL when unknown |
| `arrived_source` | `VARCHAR(16) NULL` | `soundcloud`, `youtube`, `telegram`, `label`, `import`, `unknown` |

- The scanner sets both when it creates a `library_tracks` row (`UTC_TIMESTAMP()`, and the source
  from the file's top folder by `services/common/arrival.py`). An update of an existing row leaves
  them alone.
- A retag that changes a file's `track_uid` moves it to a new track row. That is not an arrival, so
  the scanner gives the new row the earlier arrival of the two rows, in the same transaction. When
  either is NULL the new row becomes NULL: a file from before arrival dates were kept makes the
  track unknown.
- `tools/backfill_arrival_dates.py` fills NULL rows. Per track it takes the earliest of: the
  SoundCloud archive's `added_at` (`filename` equals `library_media_files.file_path`), the YouTube
  archive's `added_at` (`path` equals it), and `library_ingestion_records.recorded_at` (same
  `file_path_hash`). It accepts that date only when it is at most one hour after the track row's
  `created_at`: a later date is a redownload or a re-ingest. The source comes from the file that
  gave the date. Everything else stays NULL, and the cards say how many tracks have no arrival
  date. It is a dry run by default; `--apply --rollback FILE` writes the filled ids first, and
  `--undo FILE` sets them back to NULL.
- Both columns are nullable and have no default, so `schema_reconcile.py` adds them on deploy, with
  the index `idx_tracks_arrived_at`.

### Remixer credits (OQ 12, recommended option a)

The scanner's artist writer adds a `role='remixer'` row for each name in the file's `REMIXER` tag,
the same way it writes `featuring`. No schema change: the enum has the value.

The tagger's `InferRemixerFromTitleRule` adds a remixer to ARTIST as well, so the remixer keeps its
`featuring` row and gets a `remixer` row next to it (the primary key includes `role`). Queries that
count tracks per artist use `COUNT(DISTINCT track_id)`; the auto-approve backlog did not and now
does. The scanner only rereads a changed file, so existing tracks get their remixer rows after a
forced rescan (`POST /api/scanner/scan/all?force=true`), an operator step.

## Snapshots and caching (OQ 4)

One new table in `services/common/schema_tables.py`:

```sql
CREATE TABLE IF NOT EXISTS `wrapped_snapshots` (
  `scope` enum('user','library') NOT NULL,
  `username` varchar(255) NOT NULL,          -- '' for the library scope
  `period_key` varchar(32) NOT NULL,         -- '2026' or '2026-03-01_2026-06-30'
  `tz` varchar(64) NOT NULL,
  `data_until` datetime NOT NULL,            -- UTC end of the data the payload covers
  `closed` tinyint(1) NOT NULL DEFAULT 0,    -- the period ended before data_until
  `generated_at` datetime NOT NULL,
  `format` smallint NOT NULL,                -- payload format version
  `payload` longtext NOT NULL,
  PRIMARY KEY (`scope`,`username`,`period_key`,`tz`),
  KEY `idx_wrapped_generated` (`generated_at`)
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
```

Rules:

1. A request reads its row. A row is fresh when `format` equals the code's `WRAPPED_FORMAT` and
   either `closed = 1` or `generated_at` is less than 24 hours old.
2. A missing or stale row is computed in the request, under a per-key lock (a
   `threading.Lock` per key in `snapshots.py`, so two tabs opening at once compute once), and
   written with `INSERT ... ON DUPLICATE KEY UPDATE`.
3. A closed period is frozen. It is recomputed only by `POST /api/wrapped/refresh` or a change of
   `WRAPPED_FORMAT`.
4. A custom range is stored like a year. Rows for custom ranges not read for 30 days are deleted by
   the `events-retention` loop's daily pass (one `DELETE` on `generated_at`).
5. The shelf histogram and the library size are computed once per day in-process and shared by every
   Library snapshot of that day.
6. When #220 renames a deleted user's rows to `deleted-<id>`, the same transaction deletes that
   user's `wrapped_snapshots` rows. Library rows stay valid: a rename does not change a total.

## API Contract

All GET endpoints authenticate with `X-API-Key` (user or system key), like `/api/listening`. All
answer with `Cache-Control: private, max-age=300`.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/wrapped/periods` | `tz` | `{years: [{year, listens, own_listens}], server_tz, today}`: UTC calendar years with any listen in the library scope, newest first. `today` is in `tz` | 400 unknown `tz` |
| `GET /api/wrapped/user` | `year`, or `from` and `to`; `tz`; `username` (system key only) | `{scope:'user', period:{from,to,label,running,data_until}, generated_at, coverage:{...}, cards:[...]}` | 400: both `year` and `from`/`to`, neither, `to < from`, range over 3 years, unknown `tz`, the system key without `username`; 403: a user key naming another `username`; 503 with `Retry-After`: the computation passed 20 s (the result is still written when it finishes) |
| `GET /api/wrapped/library` | `year`, or `from` and `to` | Same shape, `scope:'library'`, `tz` is the server zone | 400 as above |
| `POST /api/wrapped/refresh` | JSON body: `scope`, `year` or `from`/`to`, optional `username` (User tab only; all accounts without it) | `202 {queued: n}`: drops the matching rows and recomputes in a background thread | 400 as above or an unknown `scope`; 403 without the `wrapped.refresh` permission (admin role only) |

`coverage` holds `{listens, linked, unmatched, measured_share, origin_known_share, bpm_share,
release_year_share, arrival_share}` for the scope, and the list of cards with status other than `ok`.
The card order in `cards` is the display order; the frontend does not sort.

No existing endpoint changes. No breaking change.

## Frontend

- Routes in `router.js`: argument views `wrapped` with path `/wrapped/<period>/<tab>`, for example
  `/wrapped/2026/user`, `/wrapped/2026/library`, `/wrapped/2026-03-01_2026-06-30/user`. `/wrapped`
  alone resolves to the current year's user tab. `PLAIN_VIEWS` gets `wrapped`.
- Entry points: `Sidebar.svelte` `tailItems` next to Listening and Memories; the Library tab on the
  phone (`MobileNav`'s library list); a home tile in `PhoneHome.svelte` and on the web home from
  1 December to 31 January, behind a `wrappedOnHomeEnabled` store persisted like
  `memoriesOnHomeEnabled` (OQ 11).
- `WrappedView.svelte`: a tab bar (two `<button aria-pressed>` pills), a period picker (years from
  `/periods`, plus "Custom range" with two date inputs), then the cards. Phone width: each card
  `min-h-[100dvh]` with `scroll-snap-type: y mandatory` on the scroller and `snap-start` on cards.
  From `md`: a two-column grid, hero cards `col-span-2`, no snap.
- Card colors: a card led by a genre uses that genre's tint from `fetchGenreTints()` as a gradient
  into `muma-spotify-dark`; other cards use `muma-spotify-panel` and `brand`. Headline numbers use
  the existing display weight (`font-black`, `text-5xl` to `text-7xl`). These are new patterns built
  from existing tokens, and per AGENTS.md rule 15 they go into `docs/styleguide.md` before the code
  (a pending entry is in its Design Backlog with this design).
- Charts are divs and SVG, like `ListeningStatsView.svelte`. No chart library. Every value a chart
  shows is also in the DOM as text.
- Tracks become playable through `resolveSongs(paths)` from `feeds.js`, which turns the
  `library_path` of each listed track into a Subsonic song with its cover. Artist images come from the
  existing artist image endpoint.
- Loading: one request per tab. Skeletons in the card shapes until it answers. A 503 retries once
  after `Retry-After`, then shows the unavailable state.
- Strings go through i18n (`wrapped.*` in `en` and `nl`; the dialect files fall back).

### Sharing (OQ 5)

- `shareCard.js` draws a card on a 1080 x 1920 `<canvas>` from the card's data (not from the DOM):
  background, headline, sentence, period, the MuMa mark. Fonts are the page's own; images are cover
  art fetched through the same origin, so the canvas stays readable.
- Web: `navigator.share({files:[png]})` where `navigator.canShare` allows it, else a download link.
- App: `platform.system.share({dataUrl, title})`. Browser implementation: the web path. Capacitor
  implementation: a new `share` method on `MumaSystemPlugin.kt` that writes the PNG to the app's
  cache directory and starts `Intent.ACTION_SEND` through a `FileProvider`.
- The canvas never draws a username, a server address or an account count of another tab.

## Performance on production sizes (2026-11-12)

| Input | Size |
|---|---|
| `scrobble_listens`, 2026 | 20.532 rows |
| `scrobble_unmatched_listens`, 2026 | 29.360 rows |
| `library_tracks` | 358.857 rows |
| `library_track_effective_bpm` | 292.943 rows |
| `library_track_genres` / `_labels` / `_channels` | 270.206 / 106.816 / 237.230 rows |
| `rules_festivals` / approved podcasts | 92 / 63 |

- Every listening card reads at most the 50.000 listens of a year through the existing
  `username` and `idx_listens_listened_at` keys, with primary-key joins to the library. The
  `only_you` subquery uses the `track_id` key (EXPLAIN: `ref`, about 2 rows per probe).
- The festival and show matchers run in Python over the played set, live-set and podcast tracks
  only: 773 listens in 2026.
- The two full scans are the shelf histogram (index-only scan of `idx_effective_bpm_bpm`, about
  276.000 index rows) and the library genre spread. Both run once per day (rule 5 above).
- A user snapshot is about 40 queries; a library snapshot about 30 plus the two daily scans. A
  first computation must stay under the 20 s budget; the integration test asserts the query count,
  and the implementation MR measures the time on production before it is merged.
- A payload is about 30 KB of JSON. A read of a fresh snapshot is one primary-key lookup.

## Implementation notes (2026-11-12)

Where the backend MR differs from the text above, and why:

- The cards do not run one query each. `data.py` reads the period once and the listening cards
  are Python over those rows: a year is at most 50.000 listens, and one read is faster than 40
  queries and gives every card the same rows.
- The Library tab shows the cards in `payload.LIBRARY_ORDER`, the list in functional.md: title,
  listeners, rankings, `most_shared`, `heatmap`, origins, forms, festival, then the collection and
  system cards. The other listening cards are User tab only.
- The stop list in `words.py` is longer than the one quoted above: it also has the release words
  (`edit`, `remix`, `extended`, `radio`, `official`, `video`, `audio`, `live`, `set`) and common
  English, Dutch and German short words (`from`, `this`, `that`, `are`, `not`, `all`, `your`,
  `our`, `der`, `die`, `das`, `les`), which would otherwise win every year.
- `festival` and `time_travel` match festival names in the title only; a path never holds a name
  the title does not.
- `/periods` counts UTC calendar years, so it needs no per-zone query.
- The system key must name a `username` on `/user` (400 without it); a user key reads its own.
- A deleted account's rows (#220) must be removed from `wrapped_snapshots` by the user deletion
  (rule 6 of Snapshots). That is part of #220, not of this router.

## Cross-App Impact

| App | Change |
|---|---|
| `music_manager` | New router and package, `wrapped_snapshots` table, `arrived_at`/`arrived_source` columns and their backfill tool (OQ 3), remixer credits in the scanner (OQ 12), `wrapped.refresh` permission, the snapshot delete in #220's user deletion |
| `frontend` | The page, routes, entry points, home tile setting, share code, i18n |
| `muma-mobile` | `share` on `MumaSystemPlugin` and a `FileProvider` entry; a new `versionCode` so the bundle with Wrapped reaches phones |
| `music-management-server` (LMS) | None. `/muma/api/wrapped/*` passes through the existing proxy route |

## Technical Acceptance Criteria

1. Every card function has a unit test with a scripted cursor for `ok`, `empty` and `below_minimum`,
   and the blocked cards return `blocked` with their reason when the source is absent.
2. `GET /api/wrapped/user` with a user key and another `username` answers 403; without a
   `username` it is scoped to the caller.
3. `GET /api/wrapped/library` counts listens of a `deleted-<id>` username in `title` and in
   `listeners.former`, and no card in its payload holds a username.
4. Both `year` and `from` answer 400; `to < from` answers 400; a range over three years answers 400.
5. A listen at 23:30 UTC on 31 December 2025 counts in 2026 for `tz=Europe/Amsterdam` and in 2025
   for `tz=UTC`.
6. A second request for the same key within 24 hours does not recompute; a closed year is never
   recomputed without `refresh` or a format change.
7. Two concurrent requests for a missing key compute once.
8. Linked-only cards return `unmatched`, and the sum of `forms` listens equals the linked count.
9. `session` joins two listens whose gap is the first one's played seconds plus 15 minutes, and
   splits them one second later.
10. `streak` across a daylight-saving change counts the changeover day once.
11. All new SELECTs run against MariaDB in `tests/integration/test_router_sql.py`, and the new table
    and columns pass `tests/integration/test_schema_snapshot.py`.
12. The share canvas output contains no username (unit test on the draw calls).
13. The page renders each card kind in Vitest from a fixture payload, and a payload with only
    `blocked` cards renders the coverage card alone.

## Related Docs

- [functional.md](functional.md): the cards and the open questions.
- [../wrapped/research.md](../wrapped/research.md): the stat catalog and its reasons.
- [../wrapped/technical.md](../wrapped/technical.md): played seconds, origins, channels.
- [../listening-stats/technical.md](../listening-stats/technical.md): scope, time zone, disclosure.
- [../memories/technical.md](../memories/technical.md): the year-tile pattern and home tile setting.
- Issue #60 (this page), #220 (tombstoned listens of deleted users).
