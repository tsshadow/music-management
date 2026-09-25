# YouTube Demands Sign-In Since 0.72.2: 26,721 ERROR Events, No Downloads

# status: fixed

The code side is fixed. The downloads only come back after a person logs in to YouTube again. That
step is in `docs/open-work.md`, and a guided script is at `/tmp/muma-person/relogin-youtube-firefox.sh`.

# reported problem
The production `events` table holds yt-dlp ERROR events that read
`ERROR: [youtube] <id>: Sign in to confirm you’re not a bot. Use --cookies-from-browser or --cookies
for the authentication.` The first one is at **2026-09-24 08:36:58 UTC**, and there are none between
2026-09-20 and then. There were 18,516 on 2026-09-24 and 8,205 on 2026-09-25 by 06:45 UTC, 26,721 in
total. Each one comes right after a WARNING `[youtube] No title found in player responses; falling
back to title from initial data`. The first error fell in the same minute as the 0.72.2 deploy.
That release changed secret handling (the stack `.env` is no longer left on the host,
`FIREFOX_PASSWORD` became required), added `mem_limit` (downloader 2g) and recreated the
containers. So the deploy looked like the cause.

# Possible reason
The evidence was measured read-only on production on 2026-09-25. All times are UTC.

**0.72.2 made the refusals visible. It did not cause them.**
- The 0.72.2 deploy is at 2026-09-24 08:36:44: three `Received SIGTERM` events from the downloader,
  plus the artist-image fetcher's Last.fm WARNING at 08:36:49 when music-manager restarted. At
  08:36:56 the new YouTube worker logged `Using cookiesfrombrowser=firefox with profile:
  /firefox-config/profile`. Two seconds later came the first `No title found` / `Sign in to confirm`
  pair, for `dOzV0vIrxjk` of `@napalmrecords`.
- That pair is also the first yt-dlp line from YouTube in the event log at all. On 2026-09-23 the
  downloader's YouTube events are only its own lines (`Downloading audio from account: …`,
  `Processing YouTube audio batch …`, about 1,500 a day), with no `[youtube]` line among them. Up to
  0.72.1 the YouTube worker ran yt-dlp with `'ignoreerrors': True` and no `logger`
  (`release-v0.72.1:services/downloader/youtube/youtube.py:141`), so every yt-dlp error went to
  stderr and never reached the event log. Commit `90f3fb686`
  ("park YouTube on a block…", bug report [040](040-youtube-never-parks-on-a-block.md)) gave YouTube
  the `AccountReport` logger, and that commit first shipped in `release-v0.72.2`.
- The downloads stopped four days earlier. The newest YouTube file that is really new in
  `library_tracks`/`library_media_files` was created at **2026-09-20 02:39:25**
  (`/mnt/music/Youtube/D-Fence/…Concrete Break…`). In `library_ingestion_records` the last new
  YouTube file is from 2026-09-20 02:31:56. After that, source `YOUTUBE` has only the 06:12–06:13
  batch on 2026-09-21, which is a retag of old files (`101Barz/… Throwback Sessie 2010 …`,
  `Monstercat End Of Month Mix - August`, and so on), and nothing at all after 2026-09-21 06:13:12.
  In the same days SoundCloud kept ingesting (14 to 166 files a day up to 2026-09-25 07:02:37), and
  the YouTube worker kept walking its channels. The 0.69.0 deploy was at 2026-09-20 01:32:16
  (SIGTERM). The last YouTube downloads arrived in the hour after that restart, and nothing has
  arrived since. The only YouTube file created on 2026-09-24 is
  `Sander van Doorn - Identity Episode 108.f140.m4a` at 08:39:35. It is an unmerged format
  fragment from a download that the 0.72.2 SIGTERM cut off, not a successful download.

**The 0.72.2 candidates, one by one.**
- (a) *Cookie mount gone.* The only changes `git diff release-v0.72.1 release-v0.72.2 --
  docker/docker-compose.yml` makes to `youtube_worker` are the logging anchor, the healthcheck,
  `mem_limit` and `IMAGE_TAG`. `YT_COOKIES: "firefox:/firefox-config/profile"`
  (`docker/docker-compose.yml:363`) and `${HOST_DATA_PATH}/firefox:/firefox-config:ro` (`:368`) are
  unchanged. The 08:36:56 line shows the recreated worker reading that profile. The SoundCloud
  worker, which uses the same mount, logged its checkpointed copy (`/tmp/muma-cookies-fizh6tac`) in
  the same second. `snapshot_cookie_profile` only returns a path when `cookies.sqlite` exists and
  can be copied, so the database is there and readable. Ruled out.
- (b) *Env var gone with the `.env`.* `YT_COOKIES` is a literal in the compose file, not
  `${…}` from `.env`, and `HOST_DATA_PATH` is resolved at deploy time. The SoundCloud worker uses
  the same mount and still downloads. Ruled out.
- (c) *`mem_limit` OOM-kills yt-dlp or deno.* An OOM kill ends the worker process. It would show
  as a restart, with a new `Using cookiesfrombrowser` line, and as a crash, not as YouTube's answer.
  The refusals come back about 0.6 s apart (08:36:58.480, 08:36:59.133, 08:36:59.916 …), which is
  the round trip of a server answer. Ruled out.
- (d) *deno missing, or a challenge-solver change.* A broken JS runtime shows up as `n challenge
  solving failed`, `Signature extraction failed` or `Requested format is not available`. Here
  YouTube returned no player response at all (`No title found in player responses`), which happens
  before any challenge is solved. yt-dlp and deno were unpinned (`latest`) until 0.73.1, so the
  exact versions that ran cannot be recovered. But the sign-in wall is YouTube refusing the
  session, not the solver failing. Ruled out as the cause.
- (e) *The Firefox profile is logged out.* The most likely cause. It cannot be proven read-only
  from here: whether the profile still holds a valid YouTube session can only be checked on the
  host. Two points support it. The wall answers every video, on every channel, since one moment on
  2026-09-20. And Google rotates the YouTube session cookies in a running browser. The YouTube
  worker read `cookies.sqlite` directly, and Firefox keeps its newest cookie writes in
  `cookies.sqlite-wal`, which yt-dlp's own copy step leaves behind. So the worker could present a
  session Firefox had already replaced. SoundCloud got a checkpointed copy for exactly that reason;
  YouTube never did. A flagged IP address would produce the same message. The probe in the person
  script tells the two apart after the login.

**Why it became 26,721 errors.** The sign-in wall is not an HTTP 403 or 429, so
`YoutubeDownloader._blocked` never parked the source. Every video of every due channel was asked
for, and each refusal went to `logging.error` through the new logger. Each one was also preceded
by its `No title found` warning. `downloads_rate_state` for `youtube` shows only one stray 403
(`last_403_at` 2026-09-25 07:02:16, a 60 s cooldown), so the sweep went on the whole time.

# solution
- `services/downloader/bot_check.py` (new). `is_bot_check` recognises the wall with either
  apostrophe. `BotCheckBreaker` counts refusals in a row across the whole sweep, thread-safe, and
  resets when a video's full metadata comes back (the one-argument match filter,
  `services/downloader/youtube/youtube.py:361`). `BotCheckTripped` is a `DownloadCancelled`, like
  `ShuttingDown`, because that is the one exception `ignoreerrors` re-raises. So the `download()`
  call ends at once and does not move on to the next video. This is proved against the real
  yt-dlp in `tests/unit/test_downloader_real_ytdlp.py::test_the_sign_in_wall_parks_youtube_once_without_an_error_per_video`.
- `AccountReport._log` (`services/downloader/account_report.py:124`). When a breaker is attached
  (YouTube channel and deep-sweep runs), the wall and its `No title found` warning are logged at
  DEBUG, below the event-log threshold, and counted. The refusal that reaches
  `bot_check_threshold` raises `BotCheckTripped`. Without a breaker (manual single downloads)
  nothing changes.
- `YoutubeDownloader._blocked` (`services/downloader/youtube/youtube.py:444`) now checks the
  breaker first and calls `SweepPolicy.park_block` (`services/downloader/sweep.py:161`). That
  records a fixed pause through `RateState.record_block` (`services/downloader/rate_state.py:298`),
  because waiting longer each time does not lift the wall, and logs **one** WARNING that says what
  to do. The WARNING reaches the alerts topic through the event log. The "Stopping the YouTube
  sweep" line and the skipped sweeps during the pause (`sweep.py:74`) log at INFO, so the alerts
  topic does not get a push every sweep interval.
- Two new YouTube timing knobs, editable in Beheer > Downloaders: `bot_check_threshold` (default 5)
  and `bot_check_pause` (default 6 h).
- `downloads_rate_state.block_reason` (new column, created or added in
  `services/downloader/db_schema.py` like the other downloader columns) stores `bot_check` or
  `cookies_missing`. `GET /api/downloaders/rate-state` returns it. Beheer shows the pause with the
  instruction ("Log opnieuw in bij YouTube in de Firefox-container…"). "Reset backoff" and the next
  clean sweep clear it. The field is additive; no consumer outside the web UI reads this endpoint.
- A clear early error when the cookies are missing. `cookie_profile_problem`
  (`youtube.py:63`) checks the profile once per round. If it is missing, has no
  `cookies.sqlite` or cannot be read, the round logs one ERROR naming the path, downloads nothing
  and pauses YouTube. A `CookieLoadError` from yt-dlp mid-sweep parks the same way instead of being
  retried three times per channel.
- `YoutubeDownloader._use_cookie_snapshot` (`youtube.py:254`). Each round reads a checkpointed
  copy of the live profile (`services/downloader/cookie_profile.py`, the same fix SoundCloud has)
  and removes it afterwards, so the newest rotated cookies are not left behind in the WAL.
- Tests: `services/downloader/tests/test_bot_check.py` (recognition, breaker, report, rate state,
  policy, cookie check, downloader wiring, snapshot), `services/music_manager/tests/test_downloaders.py`
  (`block_reason` in the endpoint) and `services/frontend/tests/unit/downloaderTiming.test.js` (the
  Beheer label).

**Still needed: a person logs in to YouTube again** in the `muma-firefox` container, over noVNC on
port 7003. `/tmp/muma-person/relogin-youtube-firefox.sh` checks the age and size of the cookie
database and whether it still holds a YouTube session (names only, never values). It then walks
through the login and verifies with one yt-dlp probe inside `muma-youtube-worker`. The probe also
runs without cookies, which separates a logged-out session from a flagged address. After a
successful probe, "Reset backoff" for YouTube in Beheer lifts the pause.
