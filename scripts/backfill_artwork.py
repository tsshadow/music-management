#!/usr/bin/env python3
"""
scripts/backfill_artwork.py

Embeds the cover a downloaded file should have had, for the files that already exist.

Both downloaders added yt-dlp's `EmbedThumbnail` post-processor and neither set
`writethumbnail`, so the post-processor looked for a thumbnail file, found none, printed
"There are no thumbnails on disk" and embedded nothing. Measured on production before the
fix: 387 of 149.626 SoundCloud tracks carried artwork, and 4.132 of 53.702 YouTube ones.
New downloads are fixed; these are the files already on disk.

The archive tables are the source of truth here rather than the audio tags: they map a file
path to the id the platform knows it by, which is what makes the lookup cheap.

  * SoundCloud: `api-v2.soundcloud.com/tracks?ids=<up to 50>` answers with an `artwork_url`
    per track, so the whole library is ~3.000 requests instead of 149.626 yt-dlp extractions
    against a host that answers a burst with 403. The client id is the one yt-dlp's own
    extractor resolves, so there is no second credential to keep.
  * YouTube: a thumbnail is addressable from the video id, so that side asks no API at all.

Only files that have no picture yet are touched, and a track whose artwork the platform does
not have is left alone -- the uploader's avatar is deliberately not substituted, because an
avatar on every track of a channel looks like the library found something when it did not.

Embedding changes the file's mtime, which is what the tagger walks on, so the tagger and then
LMS pick the new artwork up on their own. Nothing else has to be told.

Usage:
    python3 scripts/backfill_artwork.py --dry-run                  # report, write nothing
    python3 scripts/backfill_artwork.py --account gabberhead       # one channel, then look
    python3 scripts/backfill_artwork.py --platform soundcloud      # the whole platform
    python3 scripts/backfill_artwork.py --limit 500 --sleep 0.5

    --dry-run   Report what would change and write nothing. Run this first.
    --account   One channel, by folder name (SoundCloud's archive column is a numeric user
                id, so the folder is what a person means) or by the archive's own value.
    --platform  soundcloud | youtube (default: both).
    --limit     Stop after this many files have been written.
    --sleep     Seconds between HTTP requests (default 0.2).
"""

import argparse
import json
import logging
import sys
import time
import urllib.error
import urllib.request

from services.downloader.artwork import (
    chunked,
    embed_artwork,
    has_artwork,
    is_web_url,
    soundcloud_artwork_url,
    usable_image,
    youtube_artwork_urls,
)
from services.music_manager.database import get_db_connection

#: SoundCloud's id endpoint takes a comma-separated list; 50 is what its own web player asks for.
SOUNDCLOUD_BATCH = 50

#: Enough for a cover; a slow CDN node is not worth holding the whole run up for.
TIMEOUT_SECONDS = 20

PLATFORMS = ('soundcloud', 'youtube')

logger = logging.getLogger('backfill-artwork')


def parse_args(argv=None):
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--dry-run', action='store_true', help='Report what would change and write nothing.')
    parser.add_argument('--account', help='One channel, by folder name or by the archive value.')
    parser.add_argument('--platform', choices=PLATFORMS, help='Only this platform (default: both).')
    parser.add_argument('--limit', type=int, help='Stop after this many files have been written.')
    parser.add_argument('--sleep', type=float, default=0.2, help='Seconds between HTTP requests.')
    return parser.parse_args(argv)


def candidates(cursor, platform, account=None):
    """Every archived download of one platform, as `(path, platform_id, account)`.

    Rows whose filename or id is empty are left out here rather than guarded for later: a row
    without either names no file and identifies no track.

    `account` matches the folder as well as the column, because on the SoundCloud side the
    column is the numeric user id (157.712 of 157.713 rows) while the folder carries the
    uploader's name -- and "one channel" to a person means the name. Both are accepted so the
    same flag works for YouTube, where the column is the channel name.
    """
    table = f'downloads_{platform}_archive'
    query = f'SELECT filename, video_id, account FROM {table} WHERE filename <> %s AND video_id <> %s'
    params = ['', '']
    if account:
        query += ' AND (account = %s OR filename LIKE %s)'
        params += [account, f'%/{account}/%']
    cursor.execute(query, tuple(params))
    return [(row['filename'], row['video_id'], row['account']) for row in cursor.fetchall()]


def soundcloud_client_id():
    """The client id yt-dlp's SoundCloud extractor resolves for itself.

    Asking yt-dlp rather than keeping a second credential: it already refreshes this when
    SoundCloud rotates it, and the downloader would stop working long before this script did.
    """
    from yt_dlp import YoutubeDL

    with YoutubeDL({'quiet': True}) as ydl:
        extractor = ydl.get_info_extractor('Soundcloud')
        extractor.initialize()
        client_id = getattr(extractor, '_CLIENT_ID', None) or getattr(extractor, '_client_id', None)
    if not client_id:
        raise RuntimeError('yt-dlp could not resolve a SoundCloud client id')
    return client_id


def soundcloud_artwork_urls(track_ids, client_id, sleep=0.2):
    """`{track_id: artwork_url}` for a list of SoundCloud track ids, in batches.

    A batch that fails is logged and skipped rather than aborting the run: the ids come from
    an archive going back years, and a deleted track answers 404 for the whole batch it is in.
    """
    found = {}
    for batch in chunked(track_ids, SOUNDCLOUD_BATCH):
        ids = ','.join(str(track_id) for track_id in batch)
        url = f'https://api-v2.soundcloud.com/tracks?ids={ids}&client_id={client_id}'
        try:
            with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
                payload = json.load(response)
        except (urllib.error.URLError, ValueError, TimeoutError) as exc:
            logger.warning('Batch of %s ids failed: %s', len(batch), exc)
            time.sleep(sleep)
            continue
        for track in payload or []:
            artwork = soundcloud_artwork_url(track.get('artwork_url'))
            if artwork:
                found[str(track.get('id'))] = artwork
        time.sleep(sleep)
    return found


def download(url):
    """The bytes behind a URL, or None when it is not an image we would embed.

    The scheme is checked rather than assumed: `urllib` speaks `file://`, and on the
    SoundCloud side the URL came out of a third party's JSON.
    """
    if not is_web_url(url):
        logger.warning('Refusing a non-web artwork URL: %.40s', url)
        return None
    try:
        with urllib.request.urlopen(url, timeout=TIMEOUT_SECONDS) as response:  # noqa: S310
            data = response.read(8 * 1024 * 1024 + 1)
    except (urllib.error.URLError, TimeoutError) as exc:
        logger.debug('%s: %s', url, exc)
        return None
    return data if usable_image(data) else None


def write_artwork(path, data):
    """Embed `data` into the file at `path`. Returns whether it was written."""
    import mutagen

    try:
        audio = mutagen.File(path)
    except Exception as exc:  # noqa: BLE001 - a corrupt file must not stop the run
        logger.warning('%s: cannot be read (%s)', path, exc)
        return False
    if audio is None:
        logger.debug('%s: not an audio file mutagen knows', path)
        return False
    if has_artwork(audio):
        return False
    if not embed_artwork(audio, data):
        return False
    try:
        audio.save()
    except Exception as exc:  # noqa: BLE001 - a read-only or half-written file is one file
        logger.warning('%s: cannot be written (%s)', path, exc)
        return False
    return True


def needs_artwork(path):
    """Whether the file at `path` exists, is audio, and has no picture yet."""
    import mutagen

    try:
        audio = mutagen.File(path)
    except Exception:  # noqa: BLE001
        return False
    return audio is not None and not has_artwork(audio)


def run_platform(cursor, platform, args):
    """One platform's pass. Returns `(considered, written, missing_artwork)`."""
    rows = candidates(cursor, platform, args.account)
    logger.info('%s: %s archived downloads to consider', platform, len(rows))
    wanted = [(path, platform_id) for path, platform_id, _ in rows if needs_artwork(path)]
    logger.info('%s: %s of those have no picture yet', platform, len(wanted))

    urls = {}
    if platform == 'soundcloud' and wanted:
        urls = soundcloud_artwork_urls([platform_id for _, platform_id in wanted], soundcloud_client_id(), args.sleep)
        logger.info('%s: the platform has artwork for %s of them', platform, len(urls))

    written = 0
    without = 0
    for path, platform_id in wanted:
        if args.limit is not None and written >= args.limit:
            logger.info('%s: stopping at the requested limit of %s', platform, args.limit)
            break
        candidate_urls = [urls[str(platform_id)]] if str(platform_id) in urls else []
        if platform == 'youtube':
            candidate_urls = youtube_artwork_urls(platform_id)
        if not candidate_urls:
            without += 1
            continue
        if args.dry_run:
            written += 1
            logger.info('would embed %s into %s', candidate_urls[0], path)
            continue
        data = next((image for image in (download(url) for url in candidate_urls) if image), None)
        time.sleep(args.sleep)
        if data is None:
            without += 1
            continue
        if write_artwork(path, data):
            written += 1
            if written % 100 == 0:
                logger.info('%s: %s files done', platform, written)
        else:
            without += 1
    return len(wanted), written, without


def main(argv=None):
    logging.basicConfig(level=logging.INFO, format='%(asctime)s %(levelname)s %(message)s')
    args = parse_args(argv)
    conn = get_db_connection()
    if not conn:
        logger.error('No database connection')
        return 1
    platforms = [args.platform] if args.platform else list(PLATFORMS)
    totals = {}
    try:
        with conn.cursor() as cursor:
            for platform in platforms:
                totals[platform] = run_platform(cursor, platform, args)
    finally:
        conn.close()
    for platform, (wanted, written, without) in totals.items():
        verb = 'would embed' if args.dry_run else 'embedded'
        logger.info('%s: %s without a picture, %s %s, %s left without one', platform, wanted, verb, written, without)
    return 0


if __name__ == '__main__':
    sys.exit(main())
