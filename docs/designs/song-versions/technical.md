# Song versions: best-version ranking and the Versions page — Technical Design

Implements [functional.md](functional.md). The model, grouping, pin, split and LMS sync are those of
[the original design](../song-versions/technical.md);
this document covers what changed on 2026-09-26.

## Ranking (`services/music_manager/song_versions.py`)

`version_score(kind, file_path, bitrate_kbps, *, is_official, prefer_lossless)` packs the tiers into
one INT, each weight above the maximum of every tier below it, so an integer comparison is a
lexicographic one:

| Tier | Weight | Range |
|---|---|---|
| format (`format_tier`, 0 best, 5 tiers) | 100,000,000 | 0..4 |
| kind (`KIND_ORDER`, 8 kinds) | 1,000,000 | 0..7 |
| bitrate steps (`kbps // 32`, capped at 999) | 10 | 0..999 |
| official release | 1 | 0/1 |

Maximum 407,009,991, well inside a signed INT. Oldest/lowest id are the SQL tie-break
(`_BEST_TRACK`) and its Python mirror `best_track()`.

`format_tier(path, kbps, prefer_lossless)`: lossless is decided by extension before the `>= 300`
check, so a FLAC at ~1000 kbps is never mistaken for an MP3 320 under the storage setting.

`KIND_ORDER = ('pro', 'radio', 'edit', 'original', 'none', 'extended', 'instrumental', 'video')`.
`version_kind()` reads trailing brackets with a *kind vocabulary* = the grouping modifiers plus
`pro`, `music`, `audio`. This change never regrouped anything by itself. Bug report 098 later
added the same three words to the grouping modifiers, see
[song-grouping-key](../song-grouping-key/technical.md). Marker precedence: instrumental, video, pro, radio,
extended, original, edit.

`is_official_release(path, has_label, from_download_archive, label_tree_roots)`: true under any root
(the `eps_folder_path` and the import queue from `ImportQueue.from_settings`, the latter only when it
lies outside the former), else `has_label and not from_download_archive`.

`RANKING_VERSION = 2`; `ranking_signature(prefer_lossless)` → `v2-lossless` / `v2-lossy`.

## Data Model

`library_works` gains (db_init + `migrate_v44_song_version_ranking.sql`, nullable, instant ADD COLUMN):

- `ranking_signature VARCHAR(32) NULL` — the signature the work's stored scores were computed under.
  NULL on every existing row, which triggers the one-off rescore after deploy.
- `previous_canonical_track_id INT NULL`, `canonical_changed_at TIMESTAMP NULL` (indexed) — set by a
  rescore that replaced an existing canonical; cleared by pin, reset and dismiss.

## Worker (`song_version_worker.py`)

- `RankingContext(prefer_lossless, label_tree_roots)` / `ranking_context(settings)` — read once per
  pass from `ConfigStore`.
- `assign_works` stamps a *new* work with the current signature (it was just scored under it). The
  upsert never rewrites an existing work's signature.
- `rescore_once(conn, context, dry_run=False)` walks `library_works` where the signature differs, in
  batches of `SONG_VERSION_RESCORE_BATCH` (500) by ascending id, reads every member with the same
  columns as `_UNGROUPED`, updates `version_kind`/`version_score` only where they differ
  (`executemany`), decides the canonical in Python (pin if still a member, else `best_track`), writes
  changed canonicals (flagging only when one playable version replaced another -- a canonical that
  appears from or falls back to NULL is not flagged, bug report 100), and stamps the batch. Commits per
  batch; never writes `work_id`. Idempotent and resumable: a stamped work is not selected again.
- `drain_backlog` runs `group_once` (`SONG_VERSION_BATCH`, 500 tracks) batch after batch in each
  hourly tick until no ungrouped track is left, a batch assigns nothing, or
  `SONG_VERSION_TICK_BUDGET` seconds (300) have passed; each batch commits on its own. One batch per
  hour could not keep up with a label-tree rescan (bug report 101).
- `rescore_tick` runs after `drain_backlog` in each hourly tick: if anything is pending it first runs a
  dry run and logs `ranking <sig> will rescore N works and change M canonicals`, then applies and
  logs the result (logger `music-manager.song-versions`, so both reach `/api/events`).
- `python -m services.music_manager.song_version_worker --rescore-dry-run` prints the same count
  as JSON without writing.

Flipping `prefer_lossless` changes the signature, so the next tick rescores everything the same way.

## LMS sync (`song_version_sync.py`)

The sync already mirrors `library_works.canonical_track_id`, so rescored canonicals reach LMS on the
next pass. `file_rank()` (which file of the chosen track LMS shows) now takes `prefer_lossless`,
read once per pass, so it follows the same format order as the ranking.

## API Contract

See [docs/api-specification.md](../../api-specification.md#-song-versions-apisongs).

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/songs/curation` | `q, sort (versions/changed/title), changed_only, page, page_size<=100` | `{items, total, page, page_size}` | 401 no key, 422 bad sort/page |
| `GET /api/songs/ranking` | — | `{signature, prefer_lossless, pending_works, changed_works}` | 401 |
| `GET /api/songs/{id}` | — | song + versions with `format, bitrate_kbps, source, is_official, rating, plays` (additive) | 404 |
| `POST /api/songs/{id}/pin` | `{track_id: int\|null}` | `{status, work_id, pinned_track_id}` | 403 without `rules.manage` (**new**, was any key), 404 song/track, 400 other song |
| `POST /api/songs/{id}/dismiss-change` | — | `{status, work_id}` | 403, 404 |

The pin's auth change is breaking in principle; it had no consumer outside tests
(bug report 084 searched for one).

## Cross-App Impact

- Frontend: new Management tab `song-versions` (`VersionsTab.svelte`, `songVersions.js`, router,
  sidebar, en/nl strings). The id is not `versions`: that was a deleted tab, and stale links to it
  must keep landing on the management index.
- LMS: no schema or code change; the canonical and the chosen file arrive through the existing sync.
  One canonical per work in LMS is MR !1013.
- MuMa Mobile: none — it reads LMS's canonical. The two new kind values (`pro`, `video`) travel as the
  free-text `versionKind` it already stores.

## Technical Acceptance Criteria

1. `test_song_versions.py`: ranking tables for both settings, kind detection for pro and video,
   the grouping key unchanged by the new words, official-release roots.
2. `test_song_version_worker.py`: rescore flags a changed canonical, never regroups, lets a pin win,
   clears a stale pin, writes only the stamp on a second run, dry run writes nothing, the tick
   measures before it applies.
3. `tests/integration/test_song_version_worker.py`: against MariaDB, flipping the setting moves and
   flags the canonical, a second rescore is a no-op, a pin survives, and the SQL recompute agrees
   with the Python choice.
4. `test_songs_router.py` + `tests/integration/test_router_sql.py`: the new endpoints, their errors,
   and `rules.manage` on the writes.
5. `versionsTab.test.js`, `songVersions.test.js`: list, flag, open, pin, reset, accept, search.
6. `test_song_version_sync.py`: the storage setting changes which file LMS shows.

## Related Docs

- [Original design](../song-versions/technical.md)
- [Bug report 097](../../bug-reports/097-lms-canonical-one-per-work.md) — one canonical per work in LMS
