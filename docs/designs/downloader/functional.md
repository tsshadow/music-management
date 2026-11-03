# Downloader — Functional Design

See [docs/designs/README.md](../README.md) for the design-doc process this document follows. This is the
functional (user-observable) half of the downloader feature; the implementation contract is in
[technical.md](technical.md).

## Overview

The Downloader is a background service responsible for automatically fetching new music from external
sources: SoundCloud, YouTube, and Telegram. It allows users to maintain a local library that stays
in sync with their favorite artists' uploads on these platforms without manual intervention.

For SoundCloud and YouTube, the system tracks a list of accounts and periodically scans them for new
content. When a new track is found, it is downloaded, archived in a database to prevent duplicate
downloads, and automatically tagged with metadata before being moved to the library. For Telegram, the
service monitors specific channels and downloads any audio or video files shared there.

Users must follow the terms of service of each platform and download only what they are allowed to
download.

## User Stories

- As a music collector, I want the system to automatically download new tracks from my favorite SoundCloud
  and YouTube artists, so that I don't have to check their profiles manually.
- As a Telegram user, I want tracks shared in specific channels to be downloaded automatically, so that I
  can listen to them in my main music player.
- As an administrator, I want to configure the frequency and behavior of the downloader (e.g., retries,
  throttling), so that I can avoid being blocked by external platforms.
- As a user, I want to receive a notification on my phone when a new track has been successfully
  downloaded and tagged, so that I know new music is available.
- As a system, I want to keep an archive of already-downloaded tracks, so that I don't waste bandwidth
  re-downloading the same files even if they are moved or renamed in the local library.

## Functional Flows

### SoundCloud and YouTube Download

| Situation | Observable outcome |
|---|---|
| A new track is found on a tracked account | The track is downloaded, metadata is extracted, the track is archived in the database, and the user receives a notification. |
| A track is found but is already in the database archive | The track is skipped immediately. |
| A track is found but is outside the allowed duration range (e.g., too short or too long) | The track is skipped; no notification is sent. |
| SoundCloud answers "403 Forbidden" for single tracks of an account that otherwise works | Those tracks are written off for a while; the sweep carries on. |
| SoundCloud answers "403 Forbidden" for whole accounts, several in a row | SoundCloud is parked: it enters a backoff state, waiting for an increasing amount of time before the next sweep. |
| YouTube answers "403 Forbidden" and yt-dlp gives up on the request | YouTube is parked the same way. A 403 that yt-dlp recovers from (another player client, a retry) is not a refusal. |
| YouTube answers "Sign in to confirm you're not a bot" for `bot_check_threshold` videos in a row (default 5) | YouTube is paused for `bot_check_pause` (default 6 hours) with one `WARNING` that says to log in again in the Firefox container; the individual refusals are not logged as errors. Management shows the pause and the instruction; "Reset backoff" lifts it after the login. See bug report [076](../../bug-reports/076-youtube-demands-sign-in-since-0-72-2.md). |
| The Firefox profile the YouTube worker reads cookies from is missing or has no `cookies.sqlite` | One `ERROR` naming the path, nothing is downloaded, and YouTube is paused for `bot_check_pause`, instead of every video failing on its own. |
| The service encounters a "429 Too Many Requests" error | The source is parked for an extremely long time (1-2 hours) to avoid a permanent ban. |
| A deep sweep cannot list an account (refused, removed, no such tab) | The account is not marked deep-swept and stays due. A refusal feeds the backoff above; anything else falls back to the ordinary check. |
| An error is reported while downloading | It is written to the event log (and, for `WARNING` and up, to the alerts topic), for YouTube as well as SoundCloud. |
| The worker is stopped (a deploy sends SIGTERM) | The download in progress is abandoned, the pause between rounds is cut short, and the worker exits within Docker's grace period. A cut-off download leaves only a `.part` file, never a truncated file under its real name. |
| A single video is downloaded by URL (manual download or redownload) | Only that video is downloaded; its channel is **not** added to the followed YouTube channels. |

### Telegram Download

| Situation | Observable outcome |
|---|---|
| A new audio file is posted in a monitored channel | The file is downloaded to the designated Telegram folder as `<name> [<message id>].<ext>`, then tagged. |
| Two messages carry the same filename | Both are kept: the message id makes the names differ. |
| The sender's filename contains a path (`../../x.mp3`) or characters a filesystem refuses | Only the last path component is used, unsafe characters become `_`; nothing is ever written outside the channel folder. |
| A file with the same name and size already exists (also under the name used before the message id was added) | The download is skipped. |
| A file exists but the size is different (incomplete download) | The file is re-downloaded from the beginning. |

### Configuration and Control

| Situation | Observable outcome |
|---|---|
| Running with `--repeat` | The service runs all selected steps and then sleeps for a configurable duration before starting again. |
| Running with `--step soundcloud,youtube` | Only SoundCloud and YouTube steps are executed; Telegram is skipped. |
| Running with `--account <name>` | Only the specified account/channel is processed, ignoring others in the database. |

## Acceptance Criteria

1. SoundCloud and YouTube accounts listed in the database are processed automatically when the service runs.
2. Tracks already present in the `downloads_soundcloud_archive` or `downloads_youtube_archive` tables are never re-downloaded.
3. Tracks shorter than 60 seconds or longer than 6 hours (21600s) are skipped for SoundCloud and YouTube.
4. SoundCloud and YouTube tracks are automatically tagged and triggers a notification via `ntfy.sh` upon completion.
5. Telegram downloads are placed in folders named after the source channel.
6. The service handles network errors gracefully using exponential backoff for 403 errors and long pauses for 429 errors.
7. The `--break-on-existing` flag (enabled by default) stops scanning an account's playlist as soon as an already-archived track is encountered.

## Open Questions / Not Yet Decided

- ~~**Telegram tagging**~~: resolved in 0.67 -- the Telegram worker tags each audio download itself
  (`tag_downloaded_file`), the same way the SoundCloud and YouTube post-processors do.
- **User-driven account management**: Currently, accounts must be added directly to the database. Should there be a REST API or UI for managing tracked SoundCloud/YouTube accounts?
- **Redownload triggers**: While there is a redownload API in the scanner, should the downloader service itself have a more accessible way to force-redownload a specific track by URL?
