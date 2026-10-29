# YouTube Never Parks On A Block, And Its Errors Never Reach The Event Log

# status: fixed

# reported problem
A review of the downloader's error paths found that a YouTube 403 or 429 never parked the source.
The YouTube sweep kept going through every channel while YouTube refused it, and none of those
refusals appeared in the event log (`/api/events`) or on the alerts topic. SoundCloud, which runs
the same pacing code, did park. The same review found six related defects in how the downloader
fails and stops:

1. A deep sweep that YouTube or SoundCloud refused counted as a finished one. The account was marked
   deep-swept for another `deep_sweep_days`, and SoundCloud's run of blank accounts was reset.
2. A deploy's SIGTERM did not stop a download in progress. yt-dlp moved on to the next video until
   Docker sent SIGKILL.
3. The downloader slept up to an hour between rounds with `time.sleep()`, so a deploy during the
   pause always ended in SIGKILL. The importer had no SIGTERM handler at all.
4. The Telegram worker used the sender's filename as a path. A name like `../../x` could write
   outside the channel folder, and two messages with the same filename overwrote each other.
5. The SoundCloud options appeared to turn off yt-dlp's `.part` files, which would leave a
   cut-off download under its final name.
6. Every YouTube video downloaded by URL registered its uploader as a followed channel.

# Possible reason
- `youtube/youtube.py` ran yt-dlp with `'ignoreerrors': True` and no `logger`. With that option,
  yt-dlp passes a failed entry to `report_error`, which writes to stderr when no logger is set, and
  `download()` returns normally. The `except` block that calls `SweepPolicy.rate_limit_from` never
  ran, because nothing was raised. This was checked against the real yt-dlp
  (`YoutubeDL._handle_extraction_exceptions`, `trouble`). SoundCloud already passed its
  `AccountReport` as the logger, which is why SoundCloud did park.
- `deep_sweep.list_flat` got the caller's options with `ignoreerrors` still on. A refused listing
  therefore came back as `None`, which was read as an empty list: zero listed, zero wanted,
  `complete=True`. SoundCloud's `_check_account` also called `note_progress()` whatever happened.
  The `account_probe.newest_track` docstring said errors were raised, which was not true.
- `shutdown.ShuttingDown` subclassed `Exception`. With `ignoreerrors` on, yt-dlp swallows every
  exception an entry raises except `DownloadCancelled` and a few of its own.
- `downloader_service.main` called `time.sleep(sleeptime)`. `importer_service.main` called `sleep()`
  and did not install a signal handler.
- `telegram/telegram.py` built the path with `os.path.join(folder, msg.file.name)` and downloaded
  straight to it.
- The SoundCloud options set `'no_part': True`. yt-dlp's option is spelled `nopart`, so this key
  did nothing. `git log -S` shows it arrived with the initial import and gives no reason for it.
  Because the key did nothing, the `.part` behaviour was already in effect. The real fault is the
  misleading key, and the test now pins the `.part` behaviour.
- `YoutubeArchive.insert` ran `INSERT IGNORE INTO downloads_youtube_accounts (name, download_type)`
  for the uploader of every archived video. `active` defaults to 1. As a result, one manual download
  or redownload subscribed the whole channel. An uploader id spelled differently from the followed
  row (`@handle` against `channel/UC...`) became a second active row, and that channel was swept
  twice. The insert has been there since the initial import, and no design doc mentions it.

# solution
- `AccountReport` moved to `services/downloader/account_report.py` and is shared. Every YouTube
  attempt (channel run, deep-sweep video, manual URL) passes a fresh report as yt-dlp's `logger`. The
  report forwards each line to `logging`, so errors reach the event log. YouTube parks on any 429,
  and on a 403 that yt-dlp reported as an error. A 403 logged as a warning and then recovered from
  (another player client, a retry) is ignored (`AccountReport.forbidden_errors`). A manual URL
  download does not park: it logs a warning.
- `list_flat` forces `ignoreerrors` off and raises `ListingFailed` with the reported HTTP `status`.
  YouTube parks on a refused listing. SoundCloud parks on a 429 and counts a 403 as one blank
  account (`note_blank`), the same way `_settle` reads a full run that got nothing back. Any other
  listing failure falls back to the ordinary check. The account is never marked deep-swept on a
  failed listing, and `note_progress()` only runs after a listing that came back.
- The stop flag moved to `services/common/shutdown.py`, so the importer can use it too.
  `ShuttingDown` now subclasses `yt_dlp.utils.DownloadCancelled` (with an import guard for the test
  stub). Both workers wait between rounds with `shutdown.wait(seconds)`. The importer installs a
  SIGTERM handler and stops between steps.
- Telegram: `download_target` keeps only the basename, replaces unsafe characters, adds the message
  id, takes the extension from the name, then Telethon's `ext`, then the mime type, and refuses any
  path that resolves outside the folder. The download goes to `<target>.part`, which is then moved
  into place with `os.replace`. A file already present under its pre-fix name is still recognised,
  so channels are not downloaded again. The Dutch `print` calls are now English `logging` calls.
- The inert `no_part` key was removed. Unit tests pin that neither `nopart` nor `no_part` is set.
  A test against the real yt-dlp shows that the post-processor that writes the archive row only sees
  the final file, never the `.part` file.
- The dead `playlist_random` key was removed from the YouTube options. yt-dlp reads
  `playlistrandom`, so the key did nothing, and newest-first is the order `break_on_existing` needs.
- `YoutubeArchive.insert` no longer writes to `downloads_youtube_accounts`. Following a channel is
  done only in the management screen. The rows the old insert already created are still in the
  database (see the GitLab issues).
- Tests: `tests/unit/test_downloader_real_ytdlp.py` runs the real `yt_dlp.YoutubeDL` in a child
  interpreter with fake extractors. It checks that a 403 `ExtractorError` parks the YouTube source
  and reaches `logging`, that a refused flat listing raises, that `ShuttingDown` from a progress hook
  ends the whole `download()` call (and, as the control case, that a plain exception does not), and
  that a SoundCloud download goes through `.part`. The first three were run against the code with
  their fix reverted and failed there. `tests/unit/` is now
  collected by `scripts/test/music-management-unit.sh`. That script installs the pinned yt-dlp into
  a cache directory when the interpreter has none.
