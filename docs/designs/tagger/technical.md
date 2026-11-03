# Tagger — Technical Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This document implements the already-agreed [functional.md](functional.md).

## Data Model

The Tagger interacts with several tables in the MariaDB `music_management` database to facilitate artist normalization and genre inference. These are managed via `TableHelper` and `FilterTableHelper` in `services/common/Helpers/`.

| Table | Purpose | Fields Used |
|---|---|---|
| `library_artists` | Master list of known artists. | `name` |
| `rules_ignored_artists` | Artists to be ignored or automatically corrected. | `name`, `corrected_name` |
| `rules_genres` | Master list of allowed genres. | `name`, `corrected_genre` |
| `rules_ignored_genres` | Genres to be stripped from tracks. | `name` |
| `rules_genre_backlog` | Unknown genres found during tagging, for manual review. | `genre` |
| `artist_genres` (via helper) | Mapping of artists to their primary genres. | N/A (Abstraction) |
| `subgenres` (via helper) | Mapping of subgenres to main genres. | N/A (Abstraction) |

## API Contract

The Tagger API is hosted by the `music-manager` service on port 8000.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/tagger/health` | None | `{ "status": "OK", "busy": boolean }` | None |
| `POST /api/tagger/tag/all` | None | `{ "message": "Full tagging run started in background" }` | `409 Conflict`: A tagging operation is already in progress. |
| `POST /api/tagger/tag/stop` | None | `{ "message": "Stop request sent to tagger" }` | None (Returns 200 even if no run is active). |
| `POST /api/tagger/tag/file` | `?path=string` | `{ "message": "Tagging for <path> completed" }` | `404 Not Found`: File does not exist. <br> `500 Internal Server Error`: Parsing failed. |

## Retag Queue: Backoff and Parking

The queue is `tagger_processed_files`: one row per file the tagger has seen, `needs_rescan` set when
something wants the file read again, `rescan_reason` saying what. The five-minute loop's pending pass
serves it reason by reason (`ProcessedFilesHelper.pending_reasons`/`pending_paths`) before any folder
walk. A file that raises in the tagger used to stay queued and was handed out again every round,
forever, with an `ERROR` — and so an alert push — each time
([bug report 051](../../bug-reports/051-a-failing-file-is-retried-every-round-forever.md)).

- **Counting.** `attempts` and `last_attempt` on the row (migrate_v37). `tagger.record_failure` calls
  `ProcessedFilesHelper.mark_failed` for every failed attempt, on the parallel and the serial path. A
  file nothing had queued (the walk found it) is queued with reason `retry`; a queued file keeps its
  reason.
- **Backoff.** `pending_paths` skips a row while
  `last_attempt + 2^attempts × RETRY_BASE_SECONDS` (300 s, one loop period) lies in the future: the
  retries come 10, 20, 40 and 80 minutes apart.
- **Parking.** The `TAGGER_PARK_AFTER`-th failure in a row (default 5, env override) sets
  `needs_rescan = FALSE`, `rescan_reason = 'failed'` and stores the file's current mtime, so neither
  the pending pass nor the daily walk touches it again until the file changes on disk.
  `pending_summary` reports parked files as `failed`, outside `total`; the tagger page in Management shows
  the count.
- **Resetting.** `mark_processed` and every request that queues a file on purpose — `mark_for_rescan`
  (rerun-parse, "rescan all", a redownload), `mark_paths_for_rescan` (curation decisions),
  `mark_stale_for_rescan` (the deep run) — set `attempts = 0, last_attempt = NULL`, which is also what
  takes a parked row back onto the queue.
- **Logging.** The first failure is a `WARNING` with the traceback: one unreadable file is not an
  outage, and it will be retried. A retry that fails again is `INFO`: the `WARNING` already said
  everything, and every `WARNING` is an event and an alert. Parking is one more `WARNING`. No round
  logs an `ERROR` for a file, except a failure that could not be counted (database unreachable).
- **Path identity.** `filepath` is `utf8mb4_bin`. Under the old `utf8mb4_general_ci` key two files
  whose paths differed only in case, an accent or an emoji shared one row, while the in-memory
  snapshot matched exactly, so one of the pair was retagged on every walk.

## Tag Mapping and Multi-Value Splitting

- **Per-format keys** live in `services/tagger/constants.py` (`MP3Tags`, `FLACTags`, `OPUSTags`,
  `WAVTags`, `MP4Tags`); `TagCollection` reads through the reversed maps, `BaseSong.set_tag` writes
  through the forward ones.
- **m4a atoms.** Standard tags use the iTunes atoms (`©nam`, `©ART`, `©alb`, `aART`, `©gen`, `©day`,
  `cprt`). mutagen writes any atom name outside the `----:` freeform namespace as exactly 4 bytes, so
  every custom name longer than that (`REMIXER`, `ORIGINAL_TITLE`, and every unmapped name via the
  fallback in `_set_m4a_tag`) is a freeform atom `----:com.apple.iTunes:<NAME>`, stored as UTF-8
  bytes and decoded on read. `LEGACY_MP4_ATOMS` lists where older versions wrote four tags (`REMI`,
  `ORIG`, `TALB`, freeform `ALBUM`); they are read when the correct atom is missing and deleted on the
  next save, so files migrate on their next retag (bug report 053).
- **Splitting.** A tag value is split on ';' for every tag. It is split on '/' only for `GENRE`
  (`Tag.SLASH_SPLIT_TAGS`): 'AC/DC' is one artist and 'Live 24/7' one title.
- **Order is identity.** The scanner takes the first artist as the primary one and hashes it into
  `track_uid`, so rules must correct an artist in place (`Tag.replace`), never by appending the
  correction and removing the original.
- **Real-mutagen tests.** The tagger's unit tests ask for the `mutagen` stub of
  `services/tests/mock_base.py` (`pytest.mark.mock_base`); what lands on disk is tested against the
  real mutagen in `tests/unit/test_tagger_idempotence.py`, in a child interpreter.

## Cross-App Impact

- **`music-manager`**: Primary host of the tagger logic and API.
- **`downloader`**: Passes metadata to `TagSingleFile` via `extra_info` after downloading a track.
- **`importer`**: Calls the tagger to enforce standards on imported label promo pools.
- **`scanner`**: Often triggered after a tagging run to synchronize updated file metadata back to the main library database.

## Technical Acceptance Criteria

1. **Auto-detection**: `TagSingleFile` correctly identifies `SongTypeEnum` based on the file's absolute path relative to `eps_folder_path` and `music_folder_path` settings.
2. **Rule Execution**: `BaseSong.run_all_rules()` executes all registered `TagRule` objects in sequence; rules must not interfere with each other's intermediate state unless intended (e.g., `CleanTagsRule` running multiple times).
3. **File Support**: The system correctly reads and writes tags for MP3 (EasyID3), FLAC, WAV, M4A (MP4), and OPUS using the `mutagen` library.
4. **Concurrency**: The `TaggerManager` in `music-manager` uses a `threading.Lock` to ensure only one full tagging run or single-file tagging operation occurs at a time, preventing file access conflicts.
5. **Unicode Normalization**: `ReplaceInvalidUnicodeRule` identifies and replaces zero-width spaces, non-breaking spaces, and other problematic characters with their standard ASCII/UTF-8 equivalents.
6. **Error Handling**: Failed tagging operations for individual files are logged and added to the `broken_song_helper` (persisted to `broken-files.log`) without stopping the entire batch run. A file that keeps failing is retried with an exponential backoff and parked after `TAGGER_PARK_AFTER` failures (see "Retag Queue: Backoff and Parking").
7. **Idempotency**: Running the tagger multiple times on the same file with no rule changes results in no changes to the file's modification time (mtime) after the first successful pass, handled via `ProcessedFilesHelper`.

## Round Structure

`Tagger.run` is one round: reload the rule caches, queue the files the scanner found, serve the
retag queue reason by reason, walk the folders when the walk is due, log one summary line, ask LMS
to scan. What the files of a round share is set up once for the round
([bug report 063](../../bug-reports/063-tagger-reconnects-and-rebuilds-rules-per-file.md)):

- **Connections.** `RoundScope.round_scope()` (`services/common/Helpers/RoundScope.py`) makes
  `DatabaseConnector.connect()` lend each participating thread the one connection it holds for the
  round; a helper's `close()` ends the transaction, not the socket. The round's worker pool is one
  `ThreadPoolExecutor` for the whole round, whose initializer joins each worker thread to the round,
  so a round opens at most one connection per worker plus one for the round's own thread. A
  connection is never shared between threads. Threads outside the round, and every caller outside a
  round (`TagSingleFile`, the downloader, the importer), still get a fresh connection per call.
- **Rules.** `services/tagger/Song/rule_stack.py` builds each song type's rule list once per round
  and hands the same rule objects to every file; a song only carries its file and its tags. The
  lists read at the start of the round (ignore list, genre list) behave like every other rule
  cache: a change made mid-round applies from the next round. `InferArtistFromTitleRule` follows
  the `library_artists` helper's snapshot and rebuilds its name sets when a new one is published.
- **Summary.** `Tagging round: N file(s) tagged (W written, S up to date) in Xs, M ms/file,
  C database connection(s) opened`, at `INFO` when the round tagged anything and `DEBUG` otherwise.
  `ms/file` is the round's wall time divided by the files the rules ran on, so a walk over
  up-to-date folders raises it; compare rounds of the same kind.

## Genre Splitting

A genre tag is split on `;` and `/` only, never on the artist separators of `ARTIST_REGEX`
(` & `, ` and `, ` x `, ` with `, `: `, ` vs `, ` et `, `, `, ...):

- `;` is split by `Tag` itself, for every tag.
- `/` is split by `GenreRulesHelper.split_composite` inside `ResolveGenreRule`, which leaves a
  genre that curation has already decided whole.
- `CleanTagsRule` puts `ARTIST`, `ALBUM_ARTIST` and `REMIXER` through `Tag.regex()`; `GENRE` is
  only stripped and deduplicated there. `ResolveGenreRule` does not call `Tag.regex()` either.

Before this, both rules ran `Tag.regex()` over the genre tag, so 'Drum & Bass' became 'Drum' and
'Bass', 'Hardcore: Uptempo' two genres, and a curated genre with `&`, ` and ` or `: ` in its name
could never match its own row (bug report 045). `GenrePathTest` runs the whole path over a real
`TagCollection`. Files tagged before the fix keep the halves on disk; they need their genre
corrected by hand or by a re-download, since the original string is gone.

## Related Docs

- [docs/architecture.md](../../architecture.md) — Data boundaries between services.
- [docs/api-specification.md](../../api-specification.md) — Full API reference for `music-manager`.
- [services/tagger/README.md](../../../services/tagger/README.md) — Detailed list of tagging rules and their logic.
