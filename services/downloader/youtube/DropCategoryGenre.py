from yt_dlp.postprocessor import PostProcessor

# yt-dlp's FFmpegMetadataPP resolves the genre tag as
# `genre -> genres -> categories -> tags`. The YouTube extractor never sets either
# of the first two, but it always sets `categories` from the video's YouTube
# category, so every music video arrived tagged `genre=Music` and everything else
# got its keyword list. Neither is a genre, and both reached the library as an
# unknown awaiting curation.
#
# SoundCloud is unaffected: its extractor supplies a real `genre`, so the fallback
# chain never gets as far as `categories`.
LEAKING_FIELDS = ('categories', 'tags')


class DropCategoryGenrePP(PostProcessor):
    """Keeps YouTube's video category and keywords out of the genre tag.

    Registered with `when='pre_process'`, because FFmpegMetadata is configured
    through the `postprocessors` option and every post-processor added by hand
    runs after those. Stripping the fields before the download is the only point
    that is reliably earlier.
    """

    def run(self, info):
        for field in LEAKING_FIELDS:
            info.pop(field, None)
        return ([], info)
