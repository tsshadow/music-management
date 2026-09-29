# Downloader Fills The Event Log With Expected yt-dlp Lines, And Titles Real Errors "ERROR: "

# status: fixed

# reported problem
The production event log (source `downloader`, logger `root`) over 2026-09-28 00:00 to 2026-09-29
12:00 was dominated by lines that describe nothing wrong:

| level   | line                                                              | count |
|---------|-------------------------------------------------------------------|-------|
| ERROR   | `[soundcloud] <id>: This video is DRM protected`                  | 320   |
| WARNING | `[soundcloud] <id>: hls_mp3 format not found`                     | 320   |
| WARNING | `[soundcloud] <id>: http_mp3 format not found`                    | 309   |
| WARNING | `webm doesn't support embedding a thumbnail, mkv will be used`    | 157   |

Every WARNING and up is pushed to the ntfy alerts topic; the five-minute brake only stops repeats.

Separately, five ERROR events in 24 hours were titled `root: ERROR: ` with nothing after it. Their
message column held the actual failure, e.g.
`ERROR: \r[download] Got error: 4695519 bytes read, 5740658 more expected` and
`ERROR: \r[download] Got error: HTTPSConnectionPool(...): Read timed out.`

# Possible reason
Three separate causes.

**The empty title.** yt-dlp's downloader reports a fatal retry as
`self.report_error(f'\r[download] Got error: {e}')` (`yt_dlp/downloader/common.py`): the `\r`
returns a terminal cursor over the progress line. `AccountReport`, which is yt-dlp's logger, passed
the line on to `logging` untouched, and `EventLogHandler` builds the title from
`message.splitlines()[0]` -- and `splitlines` breaks on `\r`. The failure was always in the message,
never in the title or the push.

**The webm/mkv warning.** The YouTube audio options had no `format`, so yt-dlp used its default,
`bestvideo*+bestaudio/best`: every audio download fetched the whole video, merged it, and -- because
a webm cannot carry the thumbnail `EmbedThumbnail` wants -- announced that the merge becomes an mkv.
`FFmpegExtractAudio` then pulled the audio stream back out and `keepvideo: False` deleted the mkv.
No mkv or webm reaches the library: the 702 YouTube tracks added to the library in the seven days to
2026-09-29 are 693 `.m4a` and 9 `.mp3`. The real cost was the video download itself.

**The DRM tracks.** They were retried on every sweep. The first 30 DRM track ids of that week each
appear three times (2026-09-22, 2026-09-27, and so on), and of four ids checked only two had a row in
`downloads_soundcloud_unavailable` -- as `failing`, written by the deep pass, not by the ordinary
sweep. Two things kept them coming back:
- `AccountReport` recognised only 403 and 429; a DRM refusal was never recorded anywhere.
- Even a write-off would not have helped the ordinary sweep. yt-dlp raises the DRM error inside the
  extraction (`report_drm` when no non-DRM format is left), so the complete match filter -- the
  only place the write-off was checked -- is never called for that track. Each attempt costs one
  API call per stream (`http_mp3`, `hls_mp3`, each answering 404 with its own warning) plus the
  ERROR.

# solution
In `services/downloader/account_report.py`:
- `clean_message` strips `\r` from every yt-dlp line before it is logged, so the title reads
  `root: ERROR: [download] Got error: 4695519 bytes read, ...`. The line stays an ERROR: yt-dlp gave
  up on that download.
- `BENIGN_MESSAGES` is an explicit, three-entry allowlist logged at INFO instead of WARNING/ERROR:
  the webm-to-mkv notice, `(http|hls)_(mp3|aac|opus) format not found`, and `This video is DRM
  protected`. Any other yt-dlp warning keeps its level.
- DRM refusals are collected per run (`drm_tracks`), parsed from `[<extractor>] <id>: This video is
  DRM protected`.

In the SoundCloud downloader:
- `_settle` writes each DRM track off with reason `drm`, before anything can raise. Like a 403 it is
  retried after `unavailable_retry_days` (30), in case the track is made free.
- The match filter accepts yt-dlp's `incomplete=True` call, made for every playlist entry before it
  is extracted, and skips a written-off track there. A skipped entry still counts as extracted, as
  it did when it was skipped after the extraction, so an account of written-off tracks plus one new
  403 is still read as "one track unavailable" rather than a blank account. `note_listed` points a
  following 403 at the entry actually being extracted.

In the YouTube downloader, audio channels ask for `bestaudio/best`. The audio stream is the one the
merge picked, so the m4a is unchanged; video channels keep `bestvideo*+bestaudio/best` with
`merge_output_format: mkv`, which never triggered the warning.

Tests: `services/downloader/soundcloud/tests/test_account_report.py` (cleanup, allowlist, DRM
capture, `note_listed`), `test_soundcloud_config.py` (the incomplete pre-check),
`test_403_backoff.py` (a DRM track is written off and the next sweep asks for it no more),
`services/downloader/tests/test_embedded_artwork.py` and `services/tests/YoutubeVideoDownloaderTest.py`
(the audio format).
