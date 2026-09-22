"""Cover art for a file that was downloaded without any.

Both downloaders added yt-dlp's `EmbedThumbnail` post-processor without setting
`writethumbnail`, so the post-processor found nothing on disk and embedded nothing. That is
fixed for new downloads; this is how the files already on disk get their artwork.

Re-fetching each track through yt-dlp would be one extraction per file -- 149.626 of them on
the SoundCloud side alone, against a host that answers a burst with 403. Neither platform
needs that:

* SoundCloud answers `api-v2.soundcloud.com/tracks?ids=<up to 50>` with an `artwork_url` per
  track, and the track ids are already in `downloads_soundcloud_archive.video_id`. Three
  thousand requests instead of a hundred and fifty thousand.
* A YouTube thumbnail is addressable from the video id alone (`i.ytimg.com/vi/<id>/...`), so
  that side needs no API at all.

Nothing here decides *which* files to do -- see `scripts/backfill_artwork.py` -- and nothing
here talks to a database. What lives here is the part worth testing on its own: which URL to
ask for, which size to keep, and how a picture goes into each container format.
"""

from __future__ import annotations

import logging

#: SoundCloud's `artwork_url` comes back as the 100x100 `-large` variant. The same object is
#: served in other sizes by substituting the suffix; `t500x500` is the largest one that exists
#: for every upload (`original` is absent for a good number of them, which would turn a working
#: backfill into a 404 for exactly the tracks nobody has artwork for).
SOUNDCLOUD_LARGE = '-large.'
SOUNDCLOUD_PREFERRED = '-t500x500.'

#: In descending order of size. `maxresdefault` exists only for videos uploaded above 720p, and
#: a missing one is a 404 rather than a redirect, so the caller has to walk the list.
YOUTUBE_THUMBNAIL_SIZES = ('maxresdefault', 'sddefault', 'hqdefault', 'mqdefault', 'default')

#: Beyond this a "thumbnail" is not a thumbnail: a 404 page, an HTML error, a redirect to a
#: login wall. Every real cover this fetches is well under it.
MAX_IMAGE_BYTES = 8 * 1024 * 1024

#: Under this it is a placeholder rather than a cover -- YouTube serves a 1-2 kB grey
#: rectangle for a missing `maxresdefault` on some CDN nodes instead of answering 404.
MIN_IMAGE_BYTES = 2 * 1024

logger = logging.getLogger(__name__)


def is_web_url(url: str | None) -> bool:
    """Whether a URL is one this backfill may fetch.

    `urllib` speaks `file://` as happily as `https://`, and the SoundCloud side of this takes
    its URLs out of a third party's JSON. A crafted `artwork_url` would otherwise have the
    backfill read a local file and embed it into the library.
    """
    return bool(url) and url.startswith(('https://', 'http://'))


def soundcloud_artwork_url(artwork_url: str | None) -> str | None:
    """The biggest reliable variant of a SoundCloud artwork URL, or None when there is none.

    A track with no artwork of its own answers `null`; the uploader's avatar is deliberately
    not substituted for it, because an avatar on every track of a channel is worse than no
    cover at all -- it looks like the library found something when it did not.
    """
    if not is_web_url(artwork_url):
        return None
    return artwork_url.replace(SOUNDCLOUD_LARGE, SOUNDCLOUD_PREFERRED)


def youtube_artwork_urls(video_id: str | None) -> list[str]:
    """Every thumbnail URL worth trying for a video id, largest first."""
    if not video_id:
        return []
    return [f'https://i.ytimg.com/vi/{video_id}/{size}.jpg' for size in YOUTUBE_THUMBNAIL_SIZES]


def usable_image(data: bytes | None) -> bool:
    """Whether what came back is plausibly an image rather than an error page or a placeholder."""
    if not data or len(data) < MIN_IMAGE_BYTES or len(data) > MAX_IMAGE_BYTES:
        return False
    return data[:3] == b'\xff\xd8\xff' or data[:8] == b'\x89PNG\r\n\x1a\n'


def mime_type(data: bytes) -> str:
    """The type of an image this module accepted; JPEG unless the PNG signature says otherwise."""
    return 'image/png' if data[:8] == b'\x89PNG\r\n\x1a\n' else 'image/jpeg'


def has_artwork(audio) -> bool:
    """Whether a mutagen file object already carries a picture.

    Each container keeps one somewhere else: an ID3 `APIC` frame (mp3, and wav in this
    library), an MP4 `covr` atom, a FLAC picture block. A file that has one is left alone --
    the backfill adds what is missing and never replaces a cover somebody already has.
    """
    from mutagen.flac import FLAC
    from mutagen.id3 import ID3FileType
    from mutagen.mp4 import MP4

    if isinstance(audio, FLAC):
        return bool(audio.pictures)
    if isinstance(audio, MP4):
        return bool(audio.tags and 'covr' in audio.tags)
    if isinstance(audio, ID3FileType):
        return bool(audio.tags and audio.tags.getall('APIC'))
    # An unknown container: say it has one, so a file this module cannot describe is skipped
    # rather than written to on a guess.
    logger.warning('Cannot read artwork from %s; leaving it alone', type(audio).__name__)
    return True


def embed_artwork(audio, data: bytes) -> bool:
    """Put `data` into the file object as its cover. Returns whether anything was added.

    The caller saves; this only mutates the tags in memory, which is what makes it testable
    without a real MP3 on disk.
    """
    from mutagen.flac import FLAC, Picture
    from mutagen.id3 import APIC, ID3FileType
    from mutagen.mp4 import MP4, MP4Cover

    mime = mime_type(data)

    if isinstance(audio, FLAC):
        picture = Picture()
        picture.type = 3
        picture.mime = mime
        picture.data = data
        audio.add_picture(picture)
        return True

    if isinstance(audio, MP4):
        if audio.tags is None:
            audio.add_tags()
        image_format = MP4Cover.FORMAT_PNG if mime == 'image/png' else MP4Cover.FORMAT_JPEG
        audio.tags['covr'] = [MP4Cover(data, imageformat=image_format)]
        return True

    if isinstance(audio, ID3FileType):
        if audio.tags is None:
            audio.add_tags()
        audio.tags.add(APIC(encoding=3, mime=mime, type=3, desc='Cover', data=data))
        return True

    logger.warning('No way to carry a picture in %s', type(audio).__name__)
    return False


def chunked(items, size):
    """`items` in lists of at most `size`, which is how the SoundCloud id endpoint is asked."""
    batch = []
    for item in items:
        batch.append(item)
        if len(batch) >= size:
            yield batch
            batch = []
    if batch:
        yield batch
