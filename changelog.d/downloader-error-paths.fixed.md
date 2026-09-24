- **YouTube never backed off when YouTube refused it, and its download errors never reached the
  event log.** yt-dlp ran with `ignoreerrors` and no logger, so it wrote a 403 or 429 to stderr and
  returned normally. The code that parks the source only ran on an exception, so it never ran.
  YouTube now uses the same yt-dlp logger as SoundCloud. It parks on a 429 and on a 403 that yt-dlp
  gave up on, and every error goes through the event log. (bug report 040)
- **A deep sweep that was refused counted as finished.** The listing came back empty, so the account
  was marked deep-swept for another month. A refused listing now feeds the backoff and leaves the
  account due. Any other listing failure falls back to the ordinary check.
- **A deploy now stops the downloader and importer cleanly.** A download in progress is abandoned
  instead of continuing to the next video until SIGKILL. The pause between rounds wakes up on
  SIGTERM, and the importer handles SIGTERM between its steps.
- **Telegram no longer trusts the sender's filename.** Only the base name is used, with the message
  id added, so two posts with the same name no longer overwrite each other and nothing can be
  written outside the channel folder. Files are downloaded to `.part` and renamed when complete.
- **Downloading a single YouTube video no longer follows its whole channel.** Every archived video
  used to add its uploader to the followed channels, which created duplicates when the same channel
  was spelled differently.
- Removed two yt-dlp options that did nothing because of a typo (`no_part` and `playlist_random`).

<!-- release notes -->

- **YouTube now backs off when YouTube blocks it, and its download errors appear in the event
  log.**
- **A deploy stops the downloaders and the importer cleanly.** A half-finished download no longer
  ends up in the library under its final name.
- **Telegram downloads keep posts with the same name apart** and can no longer be written outside
  their channel folder.
- **Downloading a single YouTube video no longer subscribes you to its channel.**
