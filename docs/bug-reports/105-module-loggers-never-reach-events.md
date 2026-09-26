# Hourly sync summaries never reached the event log

# status: fixed

# reported problem
Verifying issues #7, #8 and #46 on 2026-09-26, the checks "the hourly `song-version sync` line
says `wrote 0`", "the `track-form push` line" and "the `track-form pass` line" found nothing in
`/api/events`. The lines existed only in `docker logs music-manager`, and the logs of every earlier
container were gone with the container at each deploy.

# Possible reason
`setup_logging` captures INFO only for the namespaces in `ALLOWED_PREFIXES` (`music-manager`,
`downloader`, `importer`, `tagger`, `scanner`, `root`). Modules that name their logger after
themselves with `logging.getLogger(__name__)` -- `song_version_sync`, `track_form_sync`,
`release_date_sync`, `feeds.snapshot`, `routers.artist_images` and the artist image fetcher -- log
as `services.music_manager.<module>`, outside every prefix, so only their WARNING and higher
reached the stream.

# solution
`services.music_manager` is an allowed prefix. The artist image fetcher
(`services.music_manager.artist_image_fetcher`) logs several INFO lines per artist it looks up, so
a new `QUIET_PREFIXES` keeps it at WARNING. The other modules log once per run or per feed built,
a few dozen rows a day.
