- **SoundCloud downloads keep their full release date again.** Since 0.72.0 the cover-art step
  rewrote each mp3 as ID3v2.3, and ffmpeg cut yt-dlp's undelimited `upload_date` (`20260831`) down
  to the year on the way. The downloaders now hand FFmpegMetadata the date as `2026-08-31`, which
  survives that rewrite, and the tagger completes a year-only SoundCloud date from the stored download info
  when the years agree -- so a retag repairs the files already downloaded. Bug report 088.
<!-- release notes -->
- New SoundCloud downloads show their full release date again instead of only the year.
