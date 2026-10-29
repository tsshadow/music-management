# New library tracks have had no normalized_title or normalized_base_title since 2026-09-26

# status: fixed

# reported problem
Measured on production (read-only) on 2026-09-30, `library_tracks` by `DATE(created_at)`:

| created | rows | `normalized_title` NULL | `normalized_base_title` NULL | `work_id` NULL |
|---|---|---|---|---|
| 2026-09-20 … 09-25 | 41–630 a day | 0 | 0 | 0 |
| 2026-09-26 | 67,331 | 14,032 | 14,032 | 0 |
| 2026-09-27 | 294 | 294 | 294 | 0 |
| 2026-09-28 | 386 | 386 | 386 | 0 |
| 2026-09-29 | 708 | 708 | 708 | 0 |
| 2026-09-30 (to 09:00) | 427 | 427 | 427 | 15 |

It looked as though the write path had stopped filling the keys on 2026-09-26. Both keys are NULL
together on every affected row, and the NULLs form one unbroken id range: every row up to id
9,715,439 (created 2026-09-26 13:xx) has both keys, every row from 9,715,440 on has neither.

# Possible reason
No write path ever filled them. The scanner's `INSERT INTO library_tracks` in
`routers/scanner.py::process_file` has never named the two columns; git history has no commit that
removed them (`git log -S normalized_title -- services/music_manager/routers/scanner.py` is empty).
The design of the scrobble rematcher (an agent plan, since removed)
left them to `scrobble_rematch.backfill_normalized()`, run at the start of each `scrobble-rematch`
tick: one `SELECT … WHERE normalized_title IS NULL LIMIT 500` per hour, plus one tick per restart.

That is 12,000 rows a day at best, which is plenty for the few hundred tracks a normal day adds and
nowhere near enough for the label-tree rescan and regroup of 2026-09-26 (the same event that
buried the song-versions worker, bug report 101): 67,331 new rows between 05:00 and 15:00. The
backfill reads the rows through the `normalized_title` index, so in id order: everything scanned
after the burst waits behind it. By 2026-09-30 it had worked through about 53,000 of them (roughly
one batch per hour plus one per deploy, of which there were many on 2026-09-26/27) with 15,853 to
go -- and, until those are done, not one track scanned since 2026-09-26 13:xx has a key.

The 15 NULL `work_id` rows of 2026-09-30 are unrelated: all were created after 08:40, the
song-versions worker's last tick, and are simply waiting for the next hourly pass.

What a missing key costs (the only readers are the scrobble matcher's tiers in
`scrobble_rematch.py`):
- `normalized` and `base_title` tiers compare against the stored column, so a listen of such a
  track whose spelling differs from the tag only in case, accents, punctuation or a version suffix
  finds nothing; the `fuzzy` tier narrows on the same columns and misses too. The `exact` tier
  still works, and a listen that misses is parked in `scrobble_unmatched_listens` and retried
  (1 h, 24 h, 168 h), so it links once the key is filled -- delayed, not lost. On production only
  4 listens since 2026-09-26 are parked.
- Not affected: song-version grouping (`song_versions.work_key` computes its own key from the title
  and artist), feed dedupe (per `work_id`), the popular-tracks / old-hits matcher (computes
  `normalize`/`base_title` in Python from `library_tracks.title`), the orphan relink (compares
  titles in Python for this very reason) and the BPM index.

# solution
- The scanner writes both keys with the row. `scrobble_matching.normalized_title_keys(title)`
  returns `(normalized_title, normalized_base_title)` cut to their 191-character columns -- the
  existing `normalize` and `base_title`, not a second normalizer -- and `process_file`'s upsert
  (`_UPSERT_TRACK`) inserts them and refreshes them with `VALUES()` on a re-scan.
- `backfill_normalized` stays as the safety net for other writers (the ml-analyzer's placeholder
  rows, anything added later) and now uses the same helper. It picks up a row missing either key,
  not only `normalized_title`.
- `rematch_once` runs the new `drain_normalized`: batch after batch, each committed on its own,
  until a batch comes back short or `SCROBBLE_BACKFILL_BUDGET` seconds (default 300) have passed --
  the same shape as bug report 101's `drain_backlog`.

No backfill script is needed: the first `scrobble-rematch` tick after the deploy (it ticks at
startup) drains the ~16,000 existing NULL rows in one pass, 32 batches of single-row UPDATEs. To
verify afterwards on production:

    SELECT COUNT(*) FROM library_tracks WHERE normalized_title IS NULL OR normalized_base_title IS NULL;

should be 0 (or only rows created in the last few seconds by the ml-analyzer), and the event log
has one `scrobble-rematch: filled the matching keys of N rows` line from that tick.
