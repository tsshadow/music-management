# Home Load — Why the Feeds Block Each Other, and the Fix

> Amends [`technical.md`](technical.md). That design deferred any snapshot table or background job
> "until a measurement shows the live query is slow". Opening the web Home is that measurement: the
> release radar, the daily mixes and the presets each take seconds and hold each other up. This
> document records what the load path actually does, where it serialises, and the three-part fix.
> Analysed 2026-09-18 by two independent readings (Claude, Codex session `01a0b17d`); the findings
> below are the ones both confirmed in code.

## What Home Fires

Desktop Home (`Dashboard.svelte`, view `home`) starts these chains when the account is known:

| Chain | Calls | Cost class |
|---|---|---|
| Session | `GET /api/auth/verify` → `GET /api/users/{id}/settings/frontend` → `GET /api/users/{id}/dynamic-playlists` (presets) | milliseconds each |
| Genre tints | `GET /api/library/genres` (once, shared through a pending promise) | cheap |
| Daily-mix shelf | tints → `GET /api/feeds` → 3 × `GET /api/feeds/daily-mix-{soft,mid,hard}?limit=10` + artist-image probe | **seconds** |
| Release radar row | `GET /api/feeds/release-radar?limit=10` → LMS `POST /rest/getSongsByPath` | **seconds** + one RTT |
| Songs / Sets rows | 2 × LMS `getSpotifyPlaylist` | fast |
| Memories | LMS `getMemories` | fast |

About ten MuMa calls and five LMS calls. Since MR !833 nginx sends `/muma/api/` straight to
`music-manager:8000`; only the LMS-owned routes (login, admin, artist image, `users/`) still pass
`MumaResource` and its 4-slot gate.

## Where It Serialises

Four mechanisms, two on the server and two in the client. Each alone is enough to make Home feel
blocked; together they compound.

### 1. The feed listing resolves the profile seven times

`GET /api/feeds` (`routers/feeds.py`, `list_feeds`) loops over all seven policies and calls
`describe_feed` for each. `describe_feed` calls `resolve_profile`, which runs the hierarchy query,
the exclusions query, the 90-day `listens_query` (two correlated `GROUP_CONCAT` subqueries per
listen row) and `build_profile` in Python. Every policy shares `profile_window_days = 90`, so all
seven resolutions return the same profile. The three band policies then call
`_listener_hardness_stats`, which loads the same listens a second time and annotates hardness on
them, to produce percentiles the listing does not even return.

One Home load runs `resolve_profile` eleven times (seven in the listing, one for the radar, three
for the band previews) and the listens query about fourteen times, all with the same answer.

### 2. A band preview is a full feed build, and it climbs the relaxation ladder

The three `daily-mix-*` calls exist only to pick a card colour: `dailyMixes.js` fetches ten tracks,
counts their genres and looks the winner up in the tint table. Server-side, `limit=10` changes
only the quota allocation; `_load_band_candidates` still loads every candidate in the window,
annotates hardness on all of them, and — when fewer than `MIN_BAND_CANDIDATES` survive the band
filter — retries at 365 days and then with no window at all, i.e. the whole library. Three of
these run in parallel on every Home load, for three hex values whose fallback (the soft/mid/hard
ramp) is already on screen.

### 3. One Python process, and the background jobs live in it

`Dockerfile.music-manager` starts uvicorn without `--workers`. Feed handlers are sync `def`, so
FastAPI runs them in the threadpool and they overlap — under one GIL. The scanner, tagger,
LMS-DB sync, radio and news loops run as threads in that same interpreter (`main.py` startup), so
a scan in progress competes with the profile build for the same core.

Two smaller defects sit on the same path. `routers/users.py`'s `verify_api_key` is `async def`
and calls the synchronous `verify_token` (a DB round trip) directly, which blocks the event loop
for every request in flight — presets and settings pay this on each call. The PyMySQL pool is
capped at 20 with `blocking=True`, and a feed handler holds its connection for the whole build
including the Python part; not measured as saturated, but the cap is real.

### 4. The client queues everything behind the slow calls, then waits for the whole batch

`mumaGate.js` admits three MuMa calls at a time, calibrated for the LMS proxy gate that most of
these calls no longer pass. With four feed builds of seconds each in the queue, `auth/verify`,
the settings read and the presets wait behind a feed build. Presets look slow while their endpoint
answers in milliseconds.

Then two rendering barriers hide what has already arrived. `Dashboard.svelte`'s `loadCurated`
assigns `sections` only after `Promise.all` over radar, songs and sets — so the two LMS rows sit
empty until the radar finishes. `DailyMixesShelf.svelte` publishes its five cards only when all
three band builds and the artist-image probe have resolved.

There is no cache at any layer: no server-side snapshot, no `Cache-Control`, and the client's
`feedsPending` deduplicates only within one page load.

## Options Considered

| Option | Verdict |
|---|---|
| Deduplicate the profile within one request | Do it. Pure refactor, no semantic change, removes ~10 of ~14 listens queries per load. |
| Server-side snapshot per `(username, slug, date)` with background refresh | Do it. The daily mixes are day-stable by design (`md5(username\|date\|track_uid)` ordering), so a per-day snapshot is what the product already promises. The radar changes as scans land, so it gets an hourly TTL. |
| A bundled `GET /api/home` | No. Solves the same thing as the snapshot but couples Home's composition to the server; the phone Home has different sections. |
| Raise the client gate / two lanes | Do it, after the snapshot. Direct-to-Python routes do not need the LMS proxy's cap; the LMS-owned routes keep it. |
| Render sections independently | Do it. The barriers are explicit `Promise.all` assignments; publishing per section is the smaller change. |
| Drop the band builds from the card path | Do it. Cards render from `GET /api/feeds` with the ramp colour; the genre tint is a refinement that arrives later or from the snapshot. |
| `--workers 2` / separate scanner container | Not now. Every uvicorn worker would start the scanner, tagger and radio loops; the background jobs need to move first. Separate work. |
| Browser `Cache-Control` / ETag | Not now. Auth is a header, not a cookie, so browser caching per account is unreliable, and an ETag computed after the build saves bytes, not seconds. |

## The Fix, in Three Mergeable Steps

### Step 1 — client: stop waiting on things that are not needed

Frontend only, no backend change required, ships first because it removes most of the *perceived*
blocking on its own.

- `Dashboard.svelte`: `loadCurated` publishes each section as its own fetch resolves. Songs and
  sets appear in the time LMS takes; the radar row fills in when it arrives.
- `dailyMixes.js` / `DailyMixesShelf.svelte` / `DailyMixesPage.svelte`: `loadDailyMixCards`
  builds the five cards from `listFeeds()` alone — title, subtitle, the soft/mid/hard ramp for
  the bands, the name-hash colour for artist and label — and returns `{cards, refine}`. The
  shelf publishes `cards` and then calls `refine(onRefine)`, which, without blocking, fetches the
  band tint from a `fetchFeed(slug, 10)` and the artist cover from the image probe and hands
  each updated card back by slug. A refinement that fails leaves the card as it was.
- `mumaGate.js`: two lanes. Calls to the LMS-owned routes (the regex in
  `reverse-proxy.conf`: `auth/login`, `admin/`, `artists/<name>/image`, `artists/<id>`,
  `tracks/*/refresh`, `users/`) keep the cap of 3. Everything else under `/api/` is a direct
  call to Python and gets a cap of 8 — bounded so a burst of misses cannot exhaust the PyMySQL
  pool, but wide enough that the session chain never queues behind a feed build.

### Step 2 — server: compute the profile once per request

- `resolve_profile` returns the listens rows it loaded (`ProfileResolution.listens`).
- `describe_feed` accepts an already-resolved `ProfileResolution`; `list_feeds` resolves once and
  passes it to all seven. `_describe` reuses `resolution.listens` for the hardness stats instead
  of reloading them. `build_feed` unchanged in behaviour.
- `routers/users.py`: `verify_api_key` becomes a plain `def`, so FastAPI runs it in the
  threadpool like `feeds.verify_api_key` already is. The `rbac`, `scanner` and `tagger`
  wrappers that awaited it follow.

No response changes. `test_feeds_build.py` and `test_feeds_router.py` stay green; one new test
asserts that listing the feeds runs `resolve_profile` exactly once.

### Step 3 — server: snapshot the feeds and refresh them in the background

One table (`feeds/snapshot.py`, created from `main.py`'s startup like the others):

```sql
CREATE TABLE IF NOT EXISTS feeds_snapshot (
    username     VARCHAR(255) NOT NULL,
    slug         VARCHAR(64)  NOT NULL,
    feed_date    DATE         NOT NULL,
    generated_at DATETIME     NOT NULL,
    params_key   VARCHAR(64)  NOT NULL,   -- digest of the settings the row was built under
    payload      LONGTEXT     NOT NULL,   -- the full GET /api/feeds/{slug} body, as JSON
    PRIMARY KEY (username, slug, feed_date)
);
```

`payload` is the complete response body for the feed at its policy size, so a hit needs no
Python beyond `json.loads`. The listing (`GET /api/feeds`) is stored under the reserved slug
`_list` in the same table, since it is derived from the same profile. `params_key` digests the
starting genres and the hardness edges (`routers/feeds.py`, `params_key()`): a row built under
other settings is stale whatever its age, so an admin who moves the edges sees them on the next
read rather than tomorrow. Anything new that shapes a build belongs in that digest.

Read path (`GET /api/feeds/{slug}`): look up `(username, slug, today)`. A row is fresh when its
`params_key` matches and the policy is a daily mix (any `daily-mix*`: valid until midnight) or,
for `release-radar`, when `generated_at` is less than `FEEDS_RADAR_TTL_SECONDS` (default 3600)
old. Fresh → return the payload. Stale or missing → build, upsert, return. A `?limit=` smaller
than the policy size returns the first `limit` tracks of the snapshot; a `limit` *larger* than
the policy size is a different feed (the quota is allocated over more places) and is built live
and not stored — nothing in the apps asks for one. The response carries `X-MuMa-Feed-Source:
snapshot|stale|live` so a slow answer can be attributed from the browser's network tab.

That last line is a deliberate behaviour change. Today `limit=10` re-runs the quota allocation
over ten places, so the Home row and the top of the mix's own page can disagree on which ten
tracks appear. With the snapshot, the Home row is literally the head of the page it links to. The
functional design's promise ("the order MuMa returns is the whole product") is kept: it is the
same order, cut shorter.

Refresh (`feeds-refresh` thread, registered through `start_thread` beside the others): on startup
and then every `FEEDS_REFRESH_INTERVAL_SECONDS` (default 900), for every username with a listen in
the last 30 days, rebuild whatever is stale by the rule above. The build takes the same lock as
the read path's miss (one `threading.Lock` per `(username, slug)`), so a request arriving during a
build reads the previous row when there is one (`stale`) and waits for the build when there is
not — never triggers a second build of the same key. One listener's failing build is logged and
skipped, not allowed to stop the pass. Yesterday's rows are deleted by the same loop.

What a listener sees: the first Home of the day after a deploy may still build live once (the
refresh thread starts at the same time), every one after that is a table read. New listens today
change tomorrow's mix, not today's — which is what "daily" already meant. New releases reach the
radar within an hour, the same cadence `release_date_sync` already imposes.

Timing is logged on every build (`feeds.build slug=… user=… total_ms=… source=live|refresh`) so
the measurement `technical.md` asked for exists from now on.

## Cross-App Impact

- **muma-mobile** calls the same endpoints and benefits without a change; its car-mode `daily-mix`
  call becomes a table read.
- **`scripts/feeds_dryrun.py`** keeps calling `build_feed` directly and bypasses the snapshot; a
  dry run is meant to show what a live build would produce.
- **`GET /api/feeds/profile`** and the exclusions endpoint are unchanged. Writing an exclusion
  deletes that user's snapshots so the next read rebuilds with it applied.

## Deliberately Not In This Change

- No `--workers`, no scanner container split. See "Options Considered".
- No browser-side caching headers.
- No change to the ranking, the quota, the relaxation ladder or the hardness edges. This is about
  computing the same answer once instead of eleven times, and reading it from a table afterwards.
