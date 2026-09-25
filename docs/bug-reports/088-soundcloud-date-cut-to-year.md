# SoundCloud downloads arrive with only the year as their date since 0.72.0

# status: fixed

# reported problem

The download notification for a new SoundCloud track shows only the year, and so does the
library. On production, `library_ingestion_records` (the tags a file arrived with, before any
rule ran) for `source = 'SOUNDCLOUD'`:

| Day | Year-only `date` | Full `date` |
|---|---|---|
| 2026-09-20 | 0 | 1701 |
| 2026-09-21 | 0 | 3890 |
| 2026-09-22 | 9 | 5 |
| 2026-09-23 | 41 | 0 |
| 2026-09-24 | 65 | 101 |
| 2026-09-25 | 65 | 0 |

The first year-only record is 2026-09-22 10:24, 37 minutes after the first record written by
0.72.0 (09:47). The 101 full dates on 09-24 are not new downloads: they are files downloaded
months earlier (archive `added_at` in April-June) that a tagger walk recorded for the first time.
YouTube is unaffected (0 of 19 year-only after 09-22).

Examples: `/mnt/music/Soundcloud/Speedcore Italia/[SCIP-083] - Jensen - WARM UP MIX - Deadtown
16.mp3` arrived with `date: ["2026"]`, while its `downloads_soundcloud_archive.info_json` holds
`upload_date: 20260831`. `[2026-08-19] Viktor Van Stroomf - Techno Wedsday.mp3` the same, with
`upload_date: 20260820`.

# Possible reason

Not yt-dlp's extractor: every archive row since 2026-09-21 (244 of 244) has an eight-digit
`upload_date`. The date is lost after the download, inside the post-processor chain.

0.72.0 set `writethumbnail: True` for the SoundCloud downloader (cover-art fix, c31e69700), so
the `EmbedThumbnailPP` that had been registered all along -- and had silently done nothing,
having no thumbnail file -- started working. The chain is `FFmpegMetadataPP` then
`EmbedThumbnailPP`. For an mp3, yt-dlp's `EmbedThumbnailPP` remuxes the file with
`-id3v2_version 3`. ID3v2.3 has no `TDRC`; ffmpeg's ID3v2.3 writer splits a date into `TYER` +
`TDAT` only when it reads `YYYY-MM-DD`, and `FFmpegMetadataPP` writes yt-dlp's undelimited
`upload_date` (`20260831`). What survives is `TYER=2026`.

Reproduced with real ffmpeg, yt-dlp 2026.8.19 and mutagen: after `FFmpegMetadataPP` the file
reads `TDRC 20260831` (ID3v2.4); after `EmbedThumbnailPP` it is ID3v2.3 and reads `2026`. With
`date=2026-08-31` instead, the ID3v2.3 file holds `TYER 2026` + `TDAT 3108`, which mutagen reads
back as `2026-08-31`, and the cover is embedded.

YouTube wires the two the other way round (`EmbedThumbnail` before `FFmpegMetadata` in its
`postprocessors` option) and sets the date again in `YoutubeSongProcessor`, which is why it kept
its dates.

# solution

- `services/downloader/metadata_date.py`: `IsoUploadDatePP`, registered for `pre_process` in both
  downloaders, sets yt-dlp's `meta_date` override to the delimited `YYYY-MM-DD` form of
  `upload_date`. `FFmpegMetadataPP` writes that instead, and it survives the ID3v2.3 rewrite. A
  source without a full `upload_date` is left as it was.
- `BaseSong._apply_extra_info`: a DATE that is a bare year, with an `upload_date` in the info dict
  from the same year, is completed to the full date. That is what the download path does as a
  second line, and what lets a retag repair the files already on disk: a retag reads the stored
  info dict back from `downloads_soundcloud_archive.info_json` (`services/tagger/download_info.py`).
  A year that differs from the upload date is left alone.
- Tests: `tests/unit/test_download_date_real_ffmpeg.py` runs the real post-processor chain on a
  generated mp3 and asserts both the defect (without the fix: `2026`) and the fix
  (`2026-08-31`); `services/downloader/tests/test_metadata_date.py` pins the post-processor and
  its registration in both downloaders; `ReleaseDateTest` and `BaseSongTest` the completion.
- Repair of the files downloaded since 2026-09-22 follows in its own MR (branch
  `fix/soundcloud-date-repair`): queue them for the tagger with rescan reason
  `soundcloud_full_date`, so the completion above rewrites their DATE from the stored info dict.
