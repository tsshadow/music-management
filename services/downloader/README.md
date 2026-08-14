# 🚀 Downloader Service

The Downloader Service is responsible for automatically fetching music from various online sources and keeping the library up-to-date.

## 📡 Supported Sources

### 📺 YouTube
- Monitors specific channels or playlists for new content.
- Uses `yt-dlp` for high-quality audio extraction.
- Maintains a local archive database to avoid duplicate downloads.

### ☁️ SoundCloud
- Downloads library_tracks from specific library_artists or URLs.
- Handles rate limiting and metadata extraction.

### 📱 Telegram
- Monitors configured Telegram channels or chats.
- Automatically downloads audio files shared in these chats.

## 📂 Structure

- `downloader_service.py`: Main entry point and worker loop.
- `youtube/`: YouTube-specific processing logic.
- `soundcloud/`: SoundCloud-specific processing logic.
- `telegram/`: Telegram-specific processing logic.

## ⏱ Timing and backoff

How often and how fast each downloader runs is configured from the UI, under
**Systeembeheer → Downloaders → Timing**. The values are stored in the
`downloads_settings` table rather than in `ConfigStore`, because the manager and the
worker containers mount different host directories for `/app/data` and therefore do
not share `config.json`; the database is the one thing they do share.

- `timing.py` holds the schema: every knob with its default, bounds, unit and
  description. This is the only place that knows the setting names.
- `rate_state.py` keeps the self-regulating backoff. A 429 doubles a per-source
  multiplier and parks the source until a cooldown expires; both are stored in
  `downloads_rate_state`, so a container restart cannot forget about them. Enough
  clean sweeps in a row halve the multiplier again.
- `account_schedule.py` records when each account was last checked *and* when it last
  uploaded, and gives every account a cooldown that follows how recently it posted:
  under a week old keeps `account_cooldown`, then `recent_cooldown` up to a month,
  `monthly_cooldown` up to three, `occasional_cooldown` up to a year and
  `dormant_cooldown` beyond that. An account whose upload date is not known yet counts
  as fresh, so a newly added one is not held back. Whatever is due comes back ordered
  by how far past its own cooldown it is, so a sweep cut short leaves behind the
  accounts that have waited least. This, more than the backoff, is what keeps the
  request volume down. Note that `dormant_cooldown` is also the longest a returning
  account can go unnoticed.
- `sweep.py` ties the three together into the pacing policy both yt-dlp-based
  downloaders share.

Every SoundCloud check starts with a probe: one flat request for the account's newest
track (`soundcloud/account_probe.py`). When `downloads_soundcloud_archive` already
holds that track the account is done, without paging its catalogue — which for a large
account is 28 API requests that would otherwise be spent finding out nothing changed.
Only a track we have not seen leads to a full run, and that run is also where the
account's upload date is learned, from the timestamp the extraction already carries.
A probe that fails for any reason other than a 403 or 429 falls through to the full
run, so the probe can never be the reason an account goes unchecked.

A 403 or 429 is never slept off inside a worker thread. It is written to the database
and raised as `RateLimited`, which ends the sweep; the next sweep sees the cooldown
and skips. `GET /api/downloaders/rate-state` shows the current multiplier and
cooldown, and `POST /api/downloaders/rate-state/{source}/reset` clears them.

A 403 also goes out over ntfy, because it means the service is refusing us outright
rather than asking us to slow down, and downloads have stopped until the cooldown
expires. The message is sent only while the 403 wait is still climbing, so a source
that has plateaued at `backoff_403_cap` stops repeating itself every sweep. A 429 is
routine self-regulation and stays silent.

The `--sleeptime` flag on `downloader_service.py` is an override for manual runs; the
worker containers take their interval from `sweep_interval` in the settings.

## 🛠 Configuration

See the root `.env.example` for source-specific settings (API keys, channel IDs, etc.).
