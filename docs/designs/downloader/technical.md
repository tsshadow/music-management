# Downloader — Technical Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This
implements the already-agreed [functional.md](functional.md). Implemented in
`services/downloader/downloader_service.py`, `services/downloader/soundcloud/`,
`services/downloader/youtube/`, and `services/downloader/telegram/`.

## Data Model

The downloader uses several tables in the `music_management` database (MariaDB):

### Tracked Accounts

| Table | Purpose |
|---|---|
| `downloads_soundcloud_accounts` (`name`, `soundcloud_id`) | List of SoundCloud accounts to scan. `soundcloud_id` is automatically populated from `uploader_id`. |
| `downloads_youtube_accounts` (`name`, `download_type`, `channel_id`, `active`) | List of YouTube account names (handles or channel names) to scan; rows with `active = 0` are skipped. Only the management screen writes it -- a download does not register its uploader (it used to, with `active = 1`, see bug report 040). |

### Download Archives

Used to prevent duplicate downloads and store original metadata.

| Table | Purpose |
|---|---|
| `downloads_soundcloud_archive` (`account`, `video_id`, `filename`, `url`, `title`) | Archives SoundCloud downloads. `account` matches `soundcloud_id`. |
| `downloads_youtube_archive` (`account`, `video_id`, `filename`, `path`, `url`, `title`) | Archives YouTube downloads. `account` is the uploader ID. |

**Invariants**:
- `video_id` is the primary identifier for a track on its respective platform (SoundCloud URL slug or YouTube video ID).
- Archive entries are created *after* a successful download but *before* tagging (via `yt-dlp` post-processors).
  yt-dlp writes `<name>.part` and renames it before any post-processor runs, so a download cut off
  mid-way leaves a `.part` file and no archive row. (SoundCloud's options carried a `no_part: True`
  for years; yt-dlp spells the option `nopart`, so it never did anything, and it was removed.)

## CLI / Service Contract

The downloader is a CLI-based service, typically run as a background worker.

| Argument | Type | Default | Purpose |
|---|---|---|---|
| `--step` | string | `""` | Comma-separated list of steps to run: `youtube`, `soundcloud`, `telegram`. |
| `--account` | string | `None` | Limit the run to a single account or channel name. |
| `--sleeptime` | int | `300` | Seconds to wait between repeating steps when using `--repeat`. |
| `--repeat` | flag | `False` | Loop indefinitely, sleeping for `--sleeptime` between runs. |
| `--break-on-existing` | flag | `True` | Stop scanning an account's playlist as soon as an already-downloaded item is found. |

### Telegram settings

Telegram reads its settings from `ConfigStore` (`services/common/config_store.py`, the settings
behind the management screen), like every other downloader setting -- not from the environment
directly. Each is a `ConfigField` whose `env` name is only where `ConfigStore` itself looks:
- `telegram_folder`: Base directory for Telegram downloads.
- `telegram_api_id`, `telegram_api_hash`: Telegram API credentials.
- `telegram_session`: Telethon session name.
- `telegram_accounts`: Comma-separated list of channels to monitor (if `--account` is not used).

A file is stored as `download_target(folder, msg.id, msg.file.name, msg.file.ext, mime)`:
the basename of the sender's name with unsafe characters replaced, the message id, and the
extension from the name, else Telethon's `ext`, else the mime type. The result is checked to lie
inside `folder` (`os.path.commonpath` on the resolved paths), written to `<target>.part` and moved
into place with `os.replace`.

## Error handling

- **yt-dlp runs with `ignoreerrors`**, so a failed entry never raises out of `download()`; it is a
  line handed to the logger. Both downloaders therefore pass an `AccountReport`
  (`services/downloader/account_report.py`) as yt-dlp's `logger`. It forwards every line to
  `logging` -- which is what puts it in the event log -- and counts the HTTP 403s and 429s it sees.
  SoundCloud reads the counters per account (`classify_account`: a 403 among readable tracks is a
  track, a blank account is one step towards `block_threshold`). YouTube parks on any 429 and on a
  403 yt-dlp reported as an *error*; a 403 it logged as a warning and then recovered from is ignored.
  Before forwarding, the report strips the `\r` yt-dlp puts in front of some lines (it split the
  event title and left `root: ERROR: ` with nothing after it), and logs the lines in
  `BENIGN_MESSAGES` at INFO instead of WARNING/ERROR: the webm-to-mkv thumbnail notice, a missing
  SoundCloud stream (`http_mp3 format not found`) and a DRM refusal. That list is explicit on
  purpose; any other yt-dlp warning still reaches the alerts topic (bug report 130).
- **DRM-protected tracks are written off.** The report collects the ids of DRM refusals, and
  SoundCloud's `_settle` remembers them in `downloads_soundcloud_unavailable` with reason `drm`,
  retried after `unavailable_retry_days` like a 403. The DRM error is raised inside the extraction,
  before the complete match filter runs, so the SoundCloud match filter also accepts yt-dlp's
  `incomplete=True` pre-check on each playlist entry; that is where a written-off track is skipped
  without a request.
- **YouTube audio channels ask for `bestaudio/best`.** Without a format, yt-dlp's default fetched and
  merged the whole video before `FFmpegExtractAudio` discarded it again. The m4a is unchanged.
- **The deep sweep's flat listing** (`deep_sweep.list_flat`) forces `ignoreerrors` off and raises
  `ListingFailed` (carrying the reported HTTP `status`) instead of returning an empty list. A 429
  parks the source; a 403 parks YouTube and counts as one blank account for SoundCloud; anything else
  falls back to the ordinary run. The account is never marked deep-swept on a failed listing, and
  SoundCloud's `note_progress()` is only called after a listing that came back.
- **One refusal, one rung.** `SweepPolicy.park` holds a lock, and once the sweep's `stop` is set it
  hands every later caller the `RateLimited` the first one got, without another `record_403` or push:
  with several worker threads each meeting the same 403, one incident used to climb the ladder a rung
  per thread. `begin()` clears it for the next sweep. `RateState` re-reads its row before every update
  and, when somebody else changed it since (the reset button in the management page), applies the
  update on top of the stored row rather than writing its stale copy back (bug report 051).
- **Stopping.** `services/common/shutdown.py` holds the process-wide stop flag. The downloader
  installs it for SIGTERM and SIGINT, the importer for SIGTERM. `shutdown.abort_hook`, a yt-dlp
  progress hook, raises `ShuttingDown`, a subclass of `yt_dlp.utils.DownloadCancelled` -- the one
  exception family `YoutubeDL.download` re-raises under `ignoreerrors`, so the whole call ends rather
  than one entry. Both workers wait between rounds with `shutdown.wait(seconds)`, which returns as
  soon as the flag is set.

## Cross-App Impact

- **`music-manager` (Tagger)**: SoundCloud and YouTube downloaders explicitly call `Tagger.parse_song` via their respective post-processors (`SoundcloudSongProcessor`, `YoutubeSongProcessor`). This ensures files are moved to the library and metadata is applied immediately.
- **`music-manager` (Scanner)**: The scanner provides a redownload API (`POST /api/library/tracks/{id}/redownload`) that uses the archives to find the original source URL -- by the exact stored path, then by the exact file name, never a substring. The redownload runs with `overwrites: True` into a hidden staging folder beside the file (`services/downloader/redownload.py`); `ReplaceExistingPP` moves the finished file over the old one with `os.replace` before the tagger's post-processor runs, so a failed download leaves the old file and the tagger only ever sees the library path.
- **`ntfy.sh`**: Notifications are sent via `notification_service.notify` from the song processors.

## Technical Acceptance Criteria

1. **Archive Check**: `SoundcloudArchive.exists()` and `YoutubeArchive.exists()` correctly return `True` for tracks already in the database, preventing re-download.
2. **Post-processing**: `SoundcloudSongProcessor` and `YoutubeSongProcessor` successfully fetch enriched metadata using `yt-dlp --dump-single-json` and pass it to the tagger.
3. **Error Handling**: 403 and 429 answers park the source through `SweepPolicy.park`
   (`services/downloader/sweep.py`) and the persisted `RateState`, as described under Error handling.
4. **Throttling**: Batches are processed with a random pause between them to avoid rate limiting (`YoutubeDownloader._throttle`).
5. **Telegram Logic**: `TelegramDownloader` skips files that already exist in the target folder with matching size.
6. **Test Coverage**: All core logic is verified by existing tests:
    - SoundCloud: `services/downloader/soundcloud/tests/`
    - YouTube and the shared sweep code: `services/downloader/tests/`, `services/tests/Youtube*Test.py`.
    - Against the real yt-dlp (the unit suite stubs it): `tests/unit/test_downloader_real_ytdlp.py`.

## Related Docs

- [docs/architecture/responsibilities.md](../../architecture/responsibilities.md) — Data boundary details between services.
- [docs/api-specification.md](../../api-specification.md) — Reference for tagger and scanner APIs.
- [AGENTS.md](../../../AGENTS.md) — Section 1 "downloader" and Section 3 "tagger".
