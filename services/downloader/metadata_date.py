"""The upload date, handed to FFmpegMetadata in a shape an ID3v2.3 rewrite keeps.

yt-dlp's `FFmpegMetadataPP` writes `date=<upload_date>`, and `upload_date` is the
undelimited `20260831`. In an ID3v2.4 tag that lands intact in TDRC. But the SoundCloud
downloader also runs `EmbedThumbnailPP`, and since `writethumbnail` was switched on in
0.72.0 that post-processor actually does something: for an mp3 it remuxes the file with
`-id3v2_version 3`. ID3v2.3 has no TDRC; ffmpeg splits a date into TYER + TDAT only when
it reads `YYYY-MM-DD`, and an undelimited date is cut down to the year. Every SoundCloud
download since 2026-09-22 arrived with `date=2026` (bug report 088).

A delimited date survives that rewrite -- TYER `2026` + TDAT `3108`, which mutagen reads
back as `2026-08-31` -- and is the ID3 standard form anyway. yt-dlp lets the caller
override any field it writes through `meta_<field>`, so this sets `meta_date` and leaves
FFmpegMetadata itself alone.

Registered with `when='pre_process'` so it is in place before either metadata
post-processor runs, whichever way a downloader wires them.
"""

from yt_dlp.postprocessor import PostProcessor

from services.tagger.Song.ReleaseDate import iso_date


class IsoUploadDatePP(PostProcessor):
    """Sets `meta_date` to the delimited upload date, so the file keeps month and day."""

    def run(self, info):
        """Fill `meta_date` from `upload_date` unless something already chose one."""
        if not info.get('meta_date'):
            date = iso_date(info.get('upload_date'))
            if date:
                info['meta_date'] = date
        return ([], info)
