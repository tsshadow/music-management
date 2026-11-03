# 🚀 Downloader Service

The Downloader Service is responsible for automatically fetching music from various online sources and keeping the library up-to-date.

## Terms of service

Follow the terms of service of each platform you download from, and download only what you are allowed to
download. You are responsible for the content you fetch and for how you use it.

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

## 🕳 The deep sweep

Stopping at the first track we already hold is what makes the ordinary sweep cheap,
and it is also what makes a gap permanent: a run parked mid-account by a 429 leaves
the rest of that catalogue behind, and every later run stops above the hole. Nothing
in the ordinary path ever revisits the tail of an account.

`deep_sweep.py` does. It lists an account flat — ids and permalinks, 200 per request,
nothing resolved — subtracts what the archive holds and what has been written off, and
resolves only what is left. That is the difference from simply turning
`break_on_existing` off, which is the shape that got us rate limited before: without
the break, yt-dlp resolves every entry on the account in full, because resolving is
the only way it learns a duration. A five-thousand-track account then costs five
thousand metadata requests to discover the six that are missing, on every run. Here it
costs twenty-five, and the resolves follow the size of the gap.

An account takes the deep path when it is due for its ordinary check *and*
`last_deep_sweep_at` is older than `deep_sweep_days` (default 30; 0 turns it off).
Gating on ordinary due-ness is what spreads the work: the tier ladder already staggers
accounts across days, so no single run pages every account at once. The cost is that a
dormant account, whose own cooldown is 30 days, can take up to 60 to come round — which
is the account whose tail has not changed in years, so that is the right way to fail.

`--deep` on `downloader_service.py` forces the path for one run, and combines with
`--account` to do a single channel by hand.

`deep_sweep_max_downloads` (default 50) bounds what one pass may fetch.
`last_deep_sweep_at` is written **only** when a pass finishes: one that is parked or
capped leaves the account deep-due, so the next *ordinary* sweep continues the tail the
following day rather than the following month. Resuming needs no bookmark, because the
diff is recomputed from the archive every time.

The known set is the union of the database table and yt-dlp's own text archive. That
second half is not tidiness: yt-dlp consults that file itself, so a track listed there
but missing from the table would be queued, silently skipped, and then be neither
downloaded nor rejected — an account that could never be finished.

`write_offs.py` is what makes finishing possible at all. Every deliberate rejection is
recorded with its reason: a 403 keeps its `unavailable_retry_days` window, a duration
rejection stores the duration it was judged on so a widened filter brings the track
back without a request spent rediscovering it, and a track that fails three passes in a
row is written off as `failed` rather than holding its account open forever. Without
that ledger a pass would rediscover the same forty teaser clips every month, spend its
budget on them, and never reach the real tail.

Each pass logs its own audit: listed, held, written off, wanted, fetched. An account
that is complete says so in arithmetic.

The pass also leaves a count behind. `take_snapshot` partitions the listing *after* the
pass -- held, excluded (a write-off that still stands under the current bounds and retry
window), remaining -- and `AccountSchedule.record_snapshot` stores it in the six
`snapshot_*` columns of `downloads_account_checks`, parked and capped passes included.
That is what `GET /api/downloaders/coverage/{source}` and the Coverage tab read; the
log line is not it. The report's own `held` is the archive before the pass and its
`written_off` counts expired decisions, so neither adds up to `listed` and neither is
stored. See docs/designs/channel-coverage.

## 🛠 Configuration

See the root `.env.example` for source-specific settings (API keys, channel IDs, etc.).
