- **The downloader filled the event log and the alerts topic with lines that describe nothing
  wrong.** In 36 hours on production: 320 `This video is DRM protected` ERRORs, 629 `http_mp3`/
  `hls_mp3 format not found` WARNINGs and 157 `webm doesn't support embedding a thumbnail`
  WARNINGs. DRM-protected SoundCloud tracks were never written off and were fetched again on
  every sweep; they are now recorded in `downloads_soundcloud_unavailable` (reason `drm`, retried
  after 30 days) and skipped before extraction, since yt-dlp fails them before the ordinary match
  filter runs. YouTube audio channels ask for `bestaudio/best` instead of yt-dlp's default video
  merge, which downloaded every video whole only to throw it away after extracting the same audio;
  the m4a files are unchanged. A short explicit allowlist of such yt-dlp lines is logged at INFO;
  every other yt-dlp warning keeps its level. And five ERRORs a day titled just `root: ERROR: `
  now carry the failure in the title: yt-dlp's leading `\r` split it off (bug report 130).

<!-- release notes -->

- **Fewer false alarms from the downloader.** DRM-protected SoundCloud tracks are no longer
  retried every sweep, YouTube audio downloads no longer fetch the whole video, and download
  errors show their cause in the notification title.
