"""What a download knew about itself, kept as JSON.

yt-dlp hands the postprocessor a full info dict and nothing keeps it: the tagger copies
four fields out of it (`BaseSong._apply_extra_info`) and the rest is discarded when the
process moves on. Everything else it knew -- SoundCloud's `genre`, `tags` and
`description`, YouTube's music-credit `artists`/`track`/`album`/`release_year`, the
chapter list of a two-hour set -- was never written down anywhere, for 53295 YouTube and
157387 SoundCloud downloads.

This turns that dict into something a database column can hold. Two problems have to be
solved for that, and both bite quietly:

- The raw dict is not JSON-serializable. yt-dlp's own `YoutubeDL.sanitize_info` is what
  makes it so -- it is what `--write-info-json` uses.
- It is large. A YouTube info dict runs 100-800 KB, nearly all of it `formats`,
  `thumbnails` and `automatic_captions` -- transport detail that is stale within hours
  and answers no question anyone asks of an archive row. Pruned, the same dict is 5-15 KB.

Nothing here decides anything about a file. It records what the downloader was told, so a
later question can be answered from it instead of from a second request to a service that
throttles.
"""

import json
import logging

#: Keys carrying transport detail rather than metadata: URLs that expire, every available
#: format, every thumbnail size, machine-generated captions. Dropping them is what takes an
#: info dict from hundreds of kilobytes to a handful.
BULK_KEYS = (
    'automatic_captions',
    'downloader_options',
    'formats',
    'fragment_base_url',
    'fragments',
    'heatmap',
    'http_headers',
    'manifest_url',
    'requested_downloads',
    'requested_formats',
    'subtitles',
    'thumbnails',
    'url',
)

#: Above this, the blob stops being metadata and starts being a payload. A description
#: longer than this says more about a channel's link dump than about the track, so it is
#: the first thing dropped; past that the row is left without info at all rather than
#: turned into something nobody wants to read out of a table.
MAX_BYTES = 65536


def _sanitized(info: dict) -> dict:
    """yt-dlp's own view of the dict, which is what makes it serializable at all.

    Imported here rather than at module scope: this module is imported by the archive
    writers, and the tagger's test suite reaches those with yt_dlp stubbed out. A missing
    yt-dlp means the dict travels as it came, never an import error in a process that was
    only going to write a row.

    `remove_private_keys` has to be passed: it defaults to False, so the plain call keeps
    `_filename` and `__files_to_move`. The filter in `prune` does not rely on that flag
    either way, which is what keeps the result the same with and without yt-dlp present.
    """
    try:
        from yt_dlp import YoutubeDL

        return YoutubeDL.sanitize_info(info, remove_private_keys=True) or {}
    except Exception as e:
        logging.debug('Could not sanitize the info dict, keeping it as it came: %s', e)
        return info


def prune(info: dict | None) -> dict | None:
    """The info dict without the bulk, ready to serialize. None when there is nothing."""
    if not info:
        return None
    sanitized = _sanitized(info)
    if not sanitized:
        return None
    return {
        key: value
        for key, value in sanitized.items()
        # yt-dlp's own bookkeeping. Dropped here rather than left to sanitize_info so the
        # stored blob is the same shape whether or not yt-dlp could be imported.
        if key not in BULK_KEYS and not str(key).startswith('_')
    }


def to_json(info: dict | None) -> str | None:
    """The download's own metadata as a JSON string, or None when it will not fit.

    `default=str` rather than a failure: sanitize_info covers the shapes yt-dlp produces,
    but an extractor can put a date or a set in there, and losing the whole dict over one
    unusual value would be the wrong trade.
    """
    pruned = prune(info)
    if not pruned:
        return None
    assert info is not None  # prune(None) is None
    try:
        blob = json.dumps(pruned, ensure_ascii=False, default=str)
    except Exception as e:
        logging.warning('Could not serialize the info dict for %s: %s', info.get('id'), e)
        return None
    if len(blob.encode('utf-8')) <= MAX_BYTES:
        return blob
    without_description = {key: value for key, value in pruned.items() if key != 'description'}
    try:
        blob = json.dumps(without_description, ensure_ascii=False, default=str)
    except Exception:
        return None
    if len(blob.encode('utf-8')) <= MAX_BYTES:
        logging.info('Dropped the description from the stored info for %s to stay under the ceiling', info.get('id'))
        return blob
    logging.warning('Info for %s is %d bytes even without its description; storing none', info.get('id'), len(blob))
    return None
