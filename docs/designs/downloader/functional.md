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
| The service encounters a "403 Forbidden" error | The service enters a backoff state, waiting for an increasing amount of time before retrying. |
| The service encounters a "429 Too Many Requests" error | The service pauses for an extremely long time (1-2 hours) to avoid a permanent ban. |

### Telegram Download

| Situation | Observable outcome |
|---|---|
| A new audio file is posted in a monitored channel | The file is downloaded to the designated Telegram folder. |
| A file with the same name and size already exists | The download is skipped. |
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

- **Telegram tagging**: Unlike SoundCloud and YouTube, Telegram downloads are not immediately tagged by the downloader; they rely on the background tagger loop. Should Telegram have its own post-processor for immediate tagging and notifications?
- **User-driven account management**: Currently, accounts must be added directly to the database. Should there be a REST API or UI for managing tracked SoundCloud/YouTube accounts?
- **Redownload triggers**: While there is a redownload API in the scanner, should the downloader service itself have a more accessible way to force-redownload a specific track by URL?
