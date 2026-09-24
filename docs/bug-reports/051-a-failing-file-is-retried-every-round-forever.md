# A Failing File Is Retried Every Round Forever

# status: fixed — failures back off and park after five; `filepath` is binary; one park per 403 incident, a mid-sweep reset sticks; redownload matches the exact path and replaces the file atomically

# reported problem
A September 2026 audit of the tagger queue and the downloaders found four defects that were still
open after release 0.72.2. None of them had produced a report of its own; each was found by reading
the code, and each is invisible until it has done its damage.

1. **A queued file that always fails is handed out every round, forever.** `Tagger._parse_worker`
   and `Tagger._try_parse` skip `mark_processed` when `parse_song` raises, which is right — the file
   was not tagged — but nothing else happened either: `needs_rescan` stayed `TRUE`, the next
   five-minute round's pending pass handed the file out again, it raised again and logged another
   `ERROR`. Every `ERROR` is an event and goes to the alerts topic, and the alert brake's five-minute
   window is about one loop period long, so a single unreadable file could buzz the phone every
   round. The pending count never went down either, which reads as a stuck tagger.
2. **`tagger_processed_files.filepath` is a case- and accent-insensitive primary key.** The table
   was created with the server default, `utf8mb4_general_ci`, which folds case and accents and gives
   every character outside the Basic Multilingual Plane the same weight — the emoji in YouTube
   titles. Two files whose paths differ only in such a character shared one row. The tagger's
   in-memory snapshot matches paths exactly, so on every walk one of the pair was "not in the table"
   and tagged again, and each `mark_processed` overwrote the other file's `mtime`. The helper's own
   comment on `queue_new_library_files` said the collation was case-insensitive; the primary key was
   never considered.
3. **Concurrent `park()` calls climb the 403 ladder several rungs for one incident.** With
   `max_workers > 1`, every thread of a sweep that meets the same 403 called `SweepPolicy.park`,
   which has no lock and does not look at `stop`. Each call ran `record_403` — one rung each — and
   sent its own push: four workers turned one refusal into a four-rung wait and four notifications.
   Separately, `POST /api/downloaders/rate-state/{source}/reset` during a sweep was undone at the end
   of the sweep: `finish()` calls `record_success()`, which wrote the worker's in-memory snapshot —
   the state from before the reset — back over the row.
4. **Redownload picks the wrong track, and on YouTube does nothing at all.**
   `POST /api/library/tracks/{id}/redownload` looked the source up with
   `filename LIKE '%<name>%' LIMIT 1`, with the name's own `_` and `%` left as wildcards: `Intro.mp3`
   matched `DJ Intro.mp3`, and whichever row came first was downloaded. YouTube's options carry
   `nooverwrites: True`, so yt-dlp answered "has already been downloaded" for the existing library
   file and changed nothing, while the endpoint reported the redownload as started.

# Possible reason
1. The failure path was written for the folder walk, which reaches a file once a day. The pending
   pass (0.67.0) reads the queue every five minutes and nothing in the queue recorded that a file
   had already failed.
2. `CREATE TABLE` without a collation takes the server default. `channels.normalized_name`
   (migrate_v13) and `library_works.work_key` (migrate_v19) were fixed for the same reason; this
   key was not looked at.
3. `park()` was written for the single-threaded sweep. The rate state is loaded once per sweep and
   written back whole, with no check whether somebody else wrote it in between.
4. The redownload lookup predates the YouTube archive's `path` column, and redownloading was only
   ever tried on SoundCloud, whose options set `nooverwrites: False`. Telling yt-dlp to overwrite is
   not enough on its own either: it deletes the existing file *before* fetching the new one
   (`YoutubeDL.existing_file`), so a failed redownload would have left no file at all —
   `tests/unit/test_downloader_real_ytdlp.py` proves both against the real yt-dlp.

# solution
1. **Backoff and parking** (`ProcessedFilesHelper.mark_failed`, `pending_paths`,
   `tagger.record_failure`). Two columns on the queue row, `attempts` and `last_attempt`
   (migrate_v37). A failure raises the count and keeps — or puts — the file on the queue (reason
   `retry` if nothing had queued it; a queued file keeps its reason). The pending pass skips a row
   until `last_attempt + 2^attempts × 300 s`: 10, 20, 40, 80 minutes. The fifth failure in a row
   (`TAGGER_PARK_AFTER`) parks the file: `needs_rescan = FALSE`, reason `failed`, and the file's
   current `mtime`, so the daily walk leaves it alone too until the file changes. Logging: the first
   failure is a `WARNING` with the traceback, a retry is `INFO`, parking is one more `WARNING`;
   no `ERROR` unless the failure could not be counted. Tagging the
   file, or any retag request (a decision, "rescan all", the deep run, rerun-parse, a redownload),
   resets the count. `GET /api/tagger/retag/pending` carries a `failed` count beside `total`, and the
   tagger page in Beheer shows it.
2. **Binary path** (migrate_v37, `ProcessedFilesHelper.create_table`). `filepath` is
   `utf8mb4_bin`. Going from a case-insensitive collation to a binary one cannot make two existing
   keys equal, so no row has to be removed; instead, before the collation changes, the rows that
   stood for two files — found by joining `library_media_files` under the column's own collation —
   are queued with reason `binary_path`, and the twin without a row of its own is picked up by the
   tagger's anti-join, now binary. `queue_new_library_files` names `COLLATE utf8mb4_bin` on that
   join explicitly, because a new server's default (`utf8mb4_uca1400_ai_ci`) and `_bin` are not
   compared implicitly by every MariaDB version. Measurement query, read-only, to run on production
   before or after the deploy:

   ```sql
   SELECT t.filepath AS stored, m.file_path AS twin
   FROM tagger_processed_files t
   JOIN library_media_files m ON m.file_path = t.filepath AND BINARY t.filepath <> m.file_path;
   ```

   Before migrate_v37 this lists every merged pair; after it, it lists none, and
   `SELECT COUNT(*) FROM tagger_processed_files WHERE rescan_reason = 'binary_path'` says how many
   were queued.
3. **One park per sweep** (`SweepPolicy.park`, `RateState._refresh`). `park()` holds a lock, and
   once `stop` is set it returns the `RateLimited` the first caller got, without another
   `record_403` or push; `begin()` clears it for the next sweep. Every `RateState` update first
   re-reads the row; if it no longer matches what this object last read or wrote (compared at the
   DATETIME columns' whole-second resolution), the stored row wins and the update is applied on top
   of it. A reset during a sweep therefore survives `finish()`, plus that sweep's one clean run.
4. **Exact source, atomic replacement** (`library._redownload_source`,
   `services/downloader/redownload.py`). The source is found by the exact stored path — the
   SoundCloud archive's `filename`, the YouTube archive's `path` — over every spelling of the
   library path. Only when none matches, by the exact file name (equal to a bare name, or the last
   path component, the `LIKE` escaped), limited to rows in the same folder or without one; more than
   one URL left is a `409` rather than a guess. The download runs with `overwrites: True` into a
   hidden staging folder beside the file; `ReplaceExistingPP` moves the finished file over the old
   one with `os.replace` after yt-dlp's own post-processors and before the tagger's, and points
   yt-dlp's `__finaldir` at the library folder — without that, `MoveFilesAfterDownloadPP` moved the
   file back into the staging folder, which is then deleted. The tagger post-processor tags and
   announces the library path, and the task queues it for a retag (reason `redownload`), which also
   takes a parked row back. The tagger walk now skips hidden folders, as the scanner already did.

Tests: `ProcessedFilesHelperTest.RetryBackoffTest`, `TaggerTest.FailedAttemptTest`,
`tests/integration/test_tagger_queue.py` (binary rows, the migration, the backoff SQL, the anti-join,
the redownload lookup against MariaDB), `test_sweep_park_once.py`,
`test_rate_state.ChangedElsewhereTest`, `test_redownload.py`, `test_library_router.RedownloadTest`
and the four redownload tests in `tests/unit/test_downloader_real_ytdlp.py`.
