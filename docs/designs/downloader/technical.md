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
| `downloads_youtube_accounts` (`name`) | List of YouTube account names (handles or channel names) to scan. |

### Download Archives

Used to prevent duplicate downloads and store original metadata.

| Table | Purpose |
|---|---|
| `downloads_soundcloud_archive` (`account`, `video_id`, `filename`, `url`, `title`) | Archives SoundCloud downloads. `account` matches `soundcloud_id`. |
| `downloads_youtube_archive` (`account`, `video_id`, `filename`, `path`, `url`, `title`) | Archives YouTube downloads. `account` is the uploader ID. |

**Invariants**:
- `video_id` is the primary identifier for a track on its respective platform (SoundCloud URL slug or YouTube video ID).
- Archive entries are created *after* a successful download but *before* tagging (via `yt-dlp` post-processors).

## CLI / Service Contract

The downloader is a CLI-based service, typically run as a background worker.

| Argument | Type | Default | Purpose |
|---|---|---|---|
| `--step` | string | `""` | Comma-separated list of steps to run: `youtube`, `soundcloud`, `telegram`. |
| `--account` | string | `None` | Limit the run to a single account or channel name. |
| `--sleeptime` | int | `300` | Seconds to wait between repeating steps when using `--repeat`. |
| `--repeat` | flag | `False` | Loop indefinitely, sleeping for `--sleeptime` between runs. |
| `--break-on-existing` | flag | `True` | Stop scanning an account's playlist as soon as an already-downloaded item is found. |

### Environment Variables (Telegram only)

Telegram configuration relies primarily on environment variables:
- `telegram_folder`: Base directory for Telegram downloads.
- `telegram_api_id`, `telegram_api_hash`: Telegram API credentials.
- `telegram_session`: Telethon session name.
- `telegram_accounts`: Comma-separated list of channels to monitor (if `--account` is not used).

## Cross-App Impact

- **`music-manager` (Tagger)**: SoundCloud and YouTube downloaders explicitly call `Tagger.parse_song` via their respective post-processors (`SoundcloudSongProcessor`, `YoutubeSongProcessor`). This ensures files are moved to the library and metadata is applied immediately.
- **`music-manager` (Scanner)**: The scanner provides a redownload API (`POST /api/library/tracks/{id}/redownload`) that uses the archives to find the original source URL.
- **`ntfy.sh`**: Notifications are sent via `notification_service.notify` from the song processors.

## Technical Acceptance Criteria

1. **Archive Check**: `SoundcloudArchive.exists()` and `YoutubeArchive.exists()` correctly return `True` for tracks already in the database, preventing re-download.
2. **Post-processing**: `SoundcloudSongProcessor` and `YoutubeSongProcessor` successfully fetch enriched metadata using `yt-dlp --dump-single-json` and pass it to the tagger.
3. **Error Handling**: 403 errors trigger the exponential backoff logic defined in `soundcloud.py` (`get_403_wait_time`).
4. **Throttling**: Batches are processed with a random pause between them to avoid rate limiting (`YoutubeDownloader._throttle`).
5. **Telegram Logic**: `TelegramDownloader` skips files that already exist in the target folder with matching size.
6. **Test Coverage**: All core logic is verified by existing tests:
    - SoundCloud: `services/downloader/soundcloud/tests/`
    - YouTube: (Implicitly covered by integration tests or manual verification as no separate test directory exists).

## Related Docs

- [docs/architecture/responsibilities.md](../../architecture/responsibilities.md) — Data boundary details between services.
- [docs/api-specification.md](../../api-specification.md) — Reference for tagger and scanner APIs.
- [AGENTS.md](../../../AGENTS.md) — Section 1 "downloader" and Section 3 "tagger".
