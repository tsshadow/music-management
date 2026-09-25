- **A repair for the SoundCloud files that lost their full date.**
  `python -m services.tagger.soundcloud_date_repair` (dry run by default, `--apply` to queue) finds
  the SoundCloud downloads since 0.72.0 whose file still carries only the year. It queues them for
  the tagger with reason `soundcloud_full_date`, and the tagger restores the date from the stored
  download info.
- **A new SoundCloud download that arrives with only the year now logs a WARNING.** The tagger
  repairs the date silently, so without this warning the defect from bug report 088 could come
  back unnoticed. The warning reaches the alerts topic and the nightly prod check.
<!-- release notes -->
- SoundCloud tracks downloaded since 22 September get their full release date back once the repair
  has been run.
