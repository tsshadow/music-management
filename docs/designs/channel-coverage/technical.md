# Channel Coverage — Technical Design

Implements [functional.md](functional.md). Builds on the deep sweep described in
[downloader/technical.md](../downloader/technical.md).

## Data Model

### `downloads_account_checks` — six new columns

Added through `_ALTER_ACCOUNT_CHECKS` in `services/downloader/db_schema.py`, the same idempotent path
that added `last_deep_sweep_at`. No `migrate_v*.sql` needed: both the workers and the manager call
`ensure_downloader_tables` on start.

| Column | Type | Meaning |
|---|---|---|
| `snapshot_listed` | INT NULL | Tracks the platform listed for the account in the last deep pass. |
| `snapshot_held` | INT NULL | Listed tracks the archive holds **after** the pass (pre-pass held ∩ listed, plus what arrived). |
| `snapshot_excluded` | INT NULL | Listed tracks not held whose write-off still stands under the current retry window and duration bounds, re-read after the pass so the failures it recorded count. |
| `snapshot_remaining` | INT NULL | `listed − held − excluded`. What a next pass would try. |
| `snapshot_state` | VARCHAR(16) NULL | `complete`, `capped` or `parked`: whether the pass got to the end of `remaining`. |
| `snapshot_at` | DATETIME NULL | When the pass settled. |

All six are written together and only by the deep pass. `NULL` in all six means "never counted".
The key stays `(source, account)` where `account` is the schedule key — for YouTube video channels
that is `<name>#video`, as it already is for `last_deep_sweep_at`.

Why post-pass rather than the numbers `DeepSweepReport` carries: the report's `held` is the pre-pass
archive and its `written_off` is `len(load_many(...))`, which counts expired decisions and overlaps
with held ids. Neither adds up to `listed`. The snapshot is a partition: every listed id is in exactly
one of held / excluded / remaining.

### `downloads_youtube_archive.added_at`

`db_init.py` already creates the column for a fresh schema; production's table predates it and has no
timestamp at all. `migrate_v31_youtube_archive_added_at.sql` adds it in two statements:

```sql
ALTER TABLE downloads_youtube_archive ADD COLUMN IF NOT EXISTS added_at DATETIME NULL;
ALTER TABLE downloads_youtube_archive ALTER COLUMN added_at SET DEFAULT CURRENT_TIMESTAMP;
```

Two statements on purpose: `ADD COLUMN ... DEFAULT CURRENT_TIMESTAMP` fills every existing row with
the moment of the ALTER, and 53.658 archive rows would then read as downloaded on deploy day. Existing
rows stay `NULL` ("onbekend"); rows inserted from then on get the time. The same pair is added to the
idempotent column list in `db_init.py`.

## API Contract

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| `GET /api/downloaders/coverage/{source}` | `source` ∈ `soundcloud`, `youtube` | see below | `400` unknown source; `503` when the database cannot be read (message in `detail`) |

Response:

```json
{
  "source": "soundcloud",
  "generated_at": "2026-09-21T14:00:00",
  "totals": {
    "configured": 1113, "counted": 1000, "complete": 812, "with_backlog": 188, "never_counted": 113,
    "listed": 158000, "held": 150200, "excluded": 4300, "remaining": 3500,
    "downloads_7d": 210, "downloads_30d": 1100,
    "write_offs": [{"reason": "too_short", "count": 1563}, ...],
    "rate_state": { ...same object as /api/downloaders/rate-state per source... }
  },
  "accounts": [
    {
      "account": "dirty-workz", "key": "dirty-workz", "download_type": null,
      "listed": 1030, "held": 309, "excluded": 12, "remaining": 709, "coverage": 0.3,
      "state": "capped", "snapshot_at": "2026-09-16T22:11:05",
      "last_checked_at": "2026-09-21T13:26:29", "last_deep_sweep_at": null,
      "last_download_at": "2026-09-19T04:12:00"
    }
  ]
}
```

- `accounts` is built from the **configured** accounts (`downloads_soundcloud_accounts`,
  `downloads_youtube_accounts` with `active = 1`), with the check row attached when there is one.
  An account with a check row but no configured row is not listed: it was deleted.
- `coverage` is `held / listed`, `null` when `listed` is 0 or there is no snapshot. Not
  `(held + excluded) / listed`: excluded is shown as its own segment.
- `complete` in the totals counts accounts with a snapshot and `remaining = 0`; `with_backlog`
  counts `remaining > 0`; `never_counted` = no snapshot. `state` is not part of that arithmetic: it
  says whether the *pass* got to the end, and is shown per row.
- `last_download_at` is `MAX(added_at)` per account from the source's archive table; for YouTube
  grouped by `(account, download_type)` and `null` where every row predates the column.
- `downloads_7d` / `downloads_30d` count archive rows with `added_at` in the window.
- `write_offs` groups `downloads_soundcloud_unavailable` by `reason` for the source.
- Each account row also carries `channel` (the channel its files are filed under, with its label/artist
  links) and SoundCloud rows are matched to the archive by `soundcloud_id`; see
  [channel-links/technical.md](../channel-links/technical.md).
- Sorting and filtering are client-side; the response is one query per table, no per-account
  queries.

## Cross-App Impact

- `services/downloader`: `account_snapshot.py` holds `AccountSnapshot` (no yt-dlp import: the manager container has none and reads these rows); `deep_sweep.py` gains `take_snapshot(...)`;
  `soundcloud.py` and `youtube.py` call it from `_settle_deep` and hand the result to
  `SweepPolicy.record_snapshot` → `AccountSchedule.record_snapshot` → store `mark_snapshot`.
  `AccountCheck` carries the snapshot; `DatabaseCheckStore.load` reads the new columns.
  `YoutubeArchive.insert` is not touched: it relies on the column default, because `deploy.sh`
  starts the containers *before* it runs `migrate_*.sql`, and an insert naming a column that
  does not exist yet would lose the archive row for every video fetched in that window.
- `services/music_manager/routers/downloaders.py`: new endpoint.
- `services/frontend`: new sub-tab `Volledigheid` in `DownloadersTab.svelte`, rendered by
  `management/DownloaderCoverage.svelte`; pure helpers in `management/downloaderCoverage.js`;
  i18n keys under `management.downloaders.coverage.*` in `nl.json` and `en.json`.
- LMS / MuMa Mobile: none.

## Technical Acceptance Criteria

1. `take_snapshot` partitions the listing: for any listing, held set, arrived set and write-off map,
   `listed == held + excluded + remaining`, an id in the text archive but not in the listing is not
   counted, and an id both held and written off counts as held.
2. A failure recorded during the pass (`note_failure` → `failing`) is counted as excluded in the
   same pass's snapshot.
3. A pass that raises `RateLimited` mid-batch still records a snapshot with `state = parked`; a
   pass cut by `deep_sweep_max_downloads` records `state = capped`; one that reached the end records
   `state = complete`.
4. `InMemoryCheckStore.mark_snapshot` and `DatabaseCheckStore.mark_snapshot` leave
   `last_checked_at`, `last_upload_at`, `last_seen_track_id` and `last_deep_sweep_at` untouched, and
   create the row when there is none (with `last_checked_at = snapshot_at`).
5. The YouTube video form of a channel writes its snapshot under `<name>#video` and the audio form
   under `<name>`.
6. `GET /api/downloaders/coverage/unknown` → 400. A store failure → 503 with the reason in
   `detail`.
7. The endpoint returns every configured account, including those without a check row (all snapshot
   fields `null`, `coverage: null`), and never an account that is no longer configured.
8. `totals.complete + totals.with_backlog + totals.never_counted == totals.configured` for any
   input.
9. `migrate_v31_youtube_archive_added_at.sql` is re-runnable and leaves existing rows at `NULL`.
10. Frontend: `DownloaderCoverage` renders the tiles and the table from a mocked response, filters
    to backlog-only, sorts by remaining, and shows "nog niet geteld" for an account without a
    snapshot and "onbekend" for a missing `last_download_at`.

## Related Docs

- [downloader/technical.md](../downloader/technical.md) — the deep sweep, write-offs and the tier ladder.
- `services/downloader/README.md` — "The deep sweep".
