# Tagger — Every Path Into It, and What a Round Costs

Companion to [technical.md](technical.md). Written 2026-09-18 from production measurements
(0.66.1), after the retag queue of 70k files was found to drain at 35 files/minute.

This document answers three questions: which paths put a file in front of the tagger, which
events say "tag it again", and where the time goes. The last section lists the fixes in order
of payoff per line of code.

## 1. The bookkeeping

One table, `tagger_processed_files` (`filepath` PK, `mtime`, `last_processed`, `needs_rescan`,
`rescan_reason`). A file needs the tagger when it is not in the table, its mtime on disk is
newer than the stored one, or `needs_rescan` is set. `mark_processed` clears the flag and
stores the mtime. The "pending" count on Beheer › Tagger is `COUNT(*) WHERE needs_rescan`.

One lock, `TaggerManager._lock`. Everything below that tags a file inside `music-manager` takes
it; the downloader and importer workers run in other containers and do not.

## 2. Data paths — how a file first meets the tagger

| # | Path | Who tags, where | Bookkeeping | Notes |
|---|------|-----------------|-------------|-------|
| D1 | SoundCloud download | `SoundcloudSongProcessor` → `Tagger.parse_song`, in `muma-soundcloud-worker` | none | The file is tagged once here and **again** by the next walk, because the worker never writes the table. The second pass is what picks up rules that changed since. |
| D2 | YouTube download | `YoutubeSongProcessor` → `Tagger.parse_song`, in `muma-youtube-worker` | none | Same as D1. Info dict is stored by `download_info` so the retag can see it. |
| D3 | Telegram download | **nobody** — `telegram.py` never constructs a `TelegramSong` | none | The file waits for the walk to reach `Telegram/`, which on 0.66.1 is after EPs, Soundcloud and Youtube. |
| D4 | Importer (label release) | `mover.py` → `LabelSong.parse()`, in `muma-importer-worker` | none | Same as D1. |
| D5 | File placed by hand / other tool | nothing until the walk | the walk sees a path not in the table | Only the walk finds it. On 0.66.1 the walk restarts at EPs on every deploy, so a file dropped in Youtube can wait days. |
| D6 | LMS "rerun parse" (web + app) | `library.rerun_parse[_path]` → `mark_for_rescan` + `tag_single` + `scan_single` | flag set, cleared by the tag | **Blocks on the lock.** With a round running for hours the request waits, then the LMS thread waits with it (see the LMS thread-pool starvation note in memory). |
| D7 | Curation "apply now" | `curation._run_retag` → `tag_single` per path, ≤ `MAX_RETAG_FILES` (2000) | via `TagSingleFile` | Takes and releases the lock per file and triggers an LMS scan per file; a running round makes every one of those waits a long one. |

## 3. Rescan triggers — what says "tag it again"

| # | Trigger | Marks | Reason | Scope on prod today |
|---|---------|-------|--------|---------------------|
| R1 | Artist/label genre rule added or deleted (`curation.py`, `management.py`) | `invalidate_by_term`: artist name = term, OR title LIKE, OR path LIKE | `artist_genre_rule`, `label_genre_rule` | 146 pending |
| R2 | Artist redirect | `invalidate_by_term` | `artist_redirect` | 0 |
| R3 | Artist curation decision (reject) | `invalidate_by_artist`, exact artist match only since !850 | `artist_decision` | 7.056 |
| R4 | Genre decision | `invalidate_by_genre_id`: linked tracks + name as term | `genre_decision` | 10.507 |
| R5 | "Rescan all" (`management.py:1124`, `POST /api/tagger/rescan`) | whole table | none | the 45k Youtube rows without a reason date from 2026-08-14: this button |
| R6 | Deep run (`deep_run_tick`, every round) | oldest `tagger_deep_run_batch` (200) rows older than 30 days | none | trickle; indistinguishable from R5 in the table |
| R7 | File changed on disk (mtime) | not marked; detected by the walk | — | external edits, re-downloads |
| R8 | rerun-parse (D6) | one path | none | — |

R1/R4 are wide on purpose (a rule that infers an artist from a title cannot be found by a join).
R5 and R6 share "no reason", so the page cannot say which of the 52k reason-less rows are a
month-old button press and which are the deep run's daily slice.

## 4. What actually consumes the file — one round on 0.66.1

`Tagger.run()` per round (the loop sleeps 300 s *after* a round ends, so the cadence is round
length + 5 minutes; `/retag/run` and `/retag/restart` start one by hand):

1. `reload_rule_caches()`
2. **Pending pass** — `pending_paths` by primary key, 500 per page, 16 threads. Stops at the
   end of the key range or on `stop_requested`; a file that failed, or one flagged behind the
   cursor while the pass ran, waits for the next round.
3. **Walk** — EPs, Soundcloud, Youtube, Telegram, generic; every file `stat()`ed and checked
   against the table (per-file query on 0.66.1; one snapshot per round from !856 on).
4. One LMS scan trigger.

### Measured on prod, 2026-09-18

| Where | Rate | Why |
|-------|------|-----|
| Pending pass over EPs (label files) | ~700 files/min | Rules find nothing to change; no write. |
| Pending pass over Soundcloud | **~35 files/min** | See the profile below. |
| CPU | 16 worker threads at ~11 % each = 1.8 cores | GIL-bound Python, not I/O. |

Profile of `SoundcloudSong.parse()` on one already-tagged MOTZ file, save disabled, 2.23 s:

| Cost | Where | What |
|------|-------|------|
| 1.61 s | `TableHelper.get_all_values()` × 3 | `library_artists` (~57k names) read **from the database three times per file**: `InferArtistFromTitleRule.__init__`, `InferArtistFromPresentsOrColonRule.__init__`, `set_cleaned_artist`. The rule objects are constructed inside `parse()`, once per song. The helper already holds the same names in `_values`, preloaded; `get_all_values` ignores the cache. |
| 0.39 s | `difflib.get_close_matches` over 37k names | Fuzzy match of the "X presents:" candidate against every artist, per file. |
| rest | rules | negligible |

At 16 threads that is ~100 full-table reads per minute against MariaDB for the tagger alone.

Separately, `TableHelper.exists()` on a cached helper is `key.lower() in (k.lower() for k in
self._values)` — a linear scan with a lowercase per element, per lookup. `CheckArtistRule` and
`AddMissingArtistToDatabaseRule` call it per artist per file.

### Half the library is "changed" on every walk — `mtime FLOAT`

`tagger_processed_files.mtime` is a single-precision `FLOAT` (confirmed on prod via
`information_schema`). At today's epoch a float32 has a step of **128 seconds**, so the stored
mtime is the real one rounded to the nearest 128 s. `needs_processing` asks `mtime > db_mtime`:

| File | real mtime | stored | walk says |
|------|-----------|--------|-----------|
| `MOTZ/5 O'clock.mp3` | 1782688928.32 | 1782688896 | changed — **retagged every round** |
| `MOTZ/Andromeda Vs Red Ophis.mp3` | 1782680035.02 | 1782680064 | unchanged — an edit in the next 29 s is invisible |

Rounding goes either way. Measured on prod over 1.200 files (400 each from EPs/Scantraxx,
Youtube, Soundcloud/Dirty Workz): **841 (70 %) read as changed on every walk**, 359 hide an
edit, 0 match exactly. `mark_processed` writes the same rounded value back, so it never
converges. This is most of why a "walk with nothing to do" takes hours, and why the walk
writes files (see below) on every round. The snapshot from !856 compares the same numbers.
Both batch paths also record the mtime read *before* the save, so a file the tagger itself
wrote is "changed" again on the next walk regardless of precision.

### The rewrite that never changes anything

`Tag.changed` is set by any mutation and only cleared by a save. A rule chain that goes
`[A, B] → [A] → [A, B]` (seen on every MOTZ file: `artist changed(set)`, then `changed(add)`)
leaves `changed = True` and `save_file` writes the file, logs `File saved`, and notifies LMS —
with the same normalized tag values as before. Every pass over such a file is a write, not a
read.

## 5. Order of the retag queue

`pending_paths` orders by primary key, i.e. by path: EPs, Livesets, Podcasts, Soundcloud,
Telegram, Top 100, Youtube. A genre decision made now on a Youtube track sits behind every
Soundcloud file queued before it — today that is 19k files at 35/min. Reason and age do not
influence the order.

## 6. Fixes, ordered by payoff per line

Reviewed with Codex (2026-09-18); its corrections are folded in.

1. **`mtime` becomes `DOUBLE`, and `mark_processed` stores the mtime read *after* the save.**
   `ALTER TABLE tagger_processed_files MODIFY COLUMN mtime DOUBLE` in a migration plus the
   `CREATE TABLE` in the helper. Existing rounded values stay rounded, so the first walk after
   the change retags the "rounded down" half once more and then stores exact values; from then
   on a walk only touches files that really changed. Two lines in `tagger.py`
   (`_try_parse`, `_parse_worker`): `file.stat().st_mtime` after `parse_song`, not before.
2. **`TableHelper.get_all_values()` returns the preloaded set when the cache is enabled.**
   Removes 1.6 s of the 2.2 s per Soundcloud file. Not as a bare one-liner: the helper is
   shared by 16 threads, and the downloader/importer containers hold their own copy. So:
   an `RLock` around cache reads, refreshes and `add`/`delete`; a `STALE_AFTER_SECONDS`
   refresh that builds the new set *before* publishing it and keeps the old one on failure
   (also stamp a failed attempt, or a database outage becomes a retry storm); `add`/`delete`
   update the cache only after the commit; return a list copy, never the live set. The
   per-song lowercase sets in `InferArtistFromTitleRule.__init__` are still rebuilt over all
   57k names per file — cache those on the helper too, keyed on the load stamp.
3. **`exists()` uses `_canonical_map`.** `key.lower() in self._canonical_map` — same
   semantics as today's linear scan, O(1).
4. **`Tag.has_changes()` compares against the value at load.** `self._initial = list(self.value)`
   at the end of `__init__` (after the constructor's own normalization), `has_changes` is
   `self.value != self._initial`, and `clear_changes` — called only after `music_file.save()`
   succeeded, not before — resets `_initial`. One supporting fix: `TagCollection.set_item`
   must reuse an existing *empty* `Tag` (`if mp3tag in self.tags`, not `if self.tags.get(...)`),
   or `[A] → [] → [A]` loses its baseline. `normalize_custom_atoms` stays unconditional on
   purpose (see the festival-labeling notes).
5. **Fuzzy match: answer the boolean, stop at the first hit.** `InferArtistFromPresentsOrColonRule`
   never uses the name `get_close_matches` returns, only whether one exists. An exact-hit
   check followed by a `SequenceMatcher` loop that applies difflib's own three ratio gates
   and returns on the first name ≥ 0.7 keeps the same answers and stops early on hits. A
   first-letter prefilter is wrong (`motz`/`potz` is 0.75); a length prefilter is what
   `real_quick_ratio` already does; rapidfuzz scores differently (Indel), so it is only
   safe as a shortlist that difflib then verifies. Unmatched candidates still scan all names.
6. **Queue order by reason, then age — with a matching cursor.** `pending_paths` should serve
   decisions (`genre_decision`, `artist_decision`, `*_rule`) before reason-less rows, oldest
   first. Changing `ORDER BY` alone breaks the `filepath > after` keyset; the loop has to
   page per reason (or carry a `(reason, filepath)` cursor). There is no queued-at column —
   `last_processed` is bumped by the mark itself — so "oldest" needs one if it is wanted.
7. **Deep run and "rescan all" get a reason.** `deep_run` and `rescan_all`, so the page and
   the order can tell them apart from a decision.
8. **Downloader and importer write `mark_processed` for the final path, after their own
   `parse_song` and after any move; Telegram tags its file at all.** Removes the second full tag of every new file. A rule
   change still reaches it through the deep run; R1–R4 cannot, because the scanner has not
   indexed it yet.
9. **A rule edit during a parse is lost.** The invalidators do not take the manager lock, so
   `mark_processed` after a parse that used the old rules clears a flag set during it. A
   generation counter captured before the parse and checked in `mark_processed` fixes it
   (`UPDATE ... WHERE needs_rescan = FALSE OR generation = %s`).
10. **`tag_single` should not wait behind a full round**, and `api_tag_file` must not call it
    from an `async def` (that parks the event loop while it waits for the lock). Bounded wait
    with a 503, or file-granular interleaving with the pool.
11. **Per-file connections.** `needs_processing` (walk, until !856), `download_info.stored_info`,
    `ingestion.record` (an `INSERT IGNORE` that serializes every tag even when the row exists),
    `mark_processed`, and the rule-specific lookups each open a `pymysql` connection; there is
    no pool. Second-order once 1–4 are in.

Items 1–4 are each a handful of lines with a unit-test file next to them (`TableHelperTest`,
`TagTest`, `TaggerTest`). The 1.6 s saving in item 2 is from one profiled file with the save
disabled; the aggregate effect is to be measured on prod after the deploy, not assumed.

## 7. Target model (agreed 2026-09-19)

Four ways in, one consumer, no walk in the hot path. "Scan" below means both halves: the
muma scanner (`library_*` tables) and the LMS scan (the app can play it).

| # | Path | Trigger | Tag | Scan | Today's gap |
|---|------|---------|-----|------|-------------|
| T1 | Import or download | the worker that produced the file | the worker, right there, then `mark_processed` on the final path | worker notifies LMS for the folder and the muma scanner for the path | Downloader notifies neither; importer notifies LMS only; Telegram tags nothing; nobody writes `mark_processed`, so the walk tags every new file a second time. |
| T2 | Total rescan | the button | whole table into the queue, reason `rescan_all` | one scan at the end of the round, as now | Works; reason is missing, so it is indistinguishable from the deep run. |
| T3 | One track by hand | app/web rerun-parse | `tag_single` | `scan_single` + LMS | Works but waits behind a running round (D6/D7). |
| T4 | Rule change | the app, on save | the app resolves the rule to its paths (`RescanInvalidator`) and queues them with the rule as reason | the round scans what it wrote | Works; queue order is the alphabet, not the decision. |

What the walk is still for: a file nobody announced (dropped in by hand). That list is an
anti-join — `library_media_files` minus `tagger_processed_files` — once the scanner has seen
it, so the walk becomes a daily safety net rather than the five-minute loop's main job. The
deep run stays as the "rules changed underneath old files" net, with its own reason.

Consequences for the queue: `rescan_reason` becomes mandatory; `pending_paths` serves
decisions (T3, T4) before bulk (T2, deep run); the page shows the count per reason, which is
already what it does.
