"""What the downloader was told, handed back to a later tagging round.

A SoundCloud or YouTube file is tagged twice in its life. The first time, the yt-dlp
postprocessor has the info dict in hand and passes it in. Every time after that --
`_parse_channel_folders` walking the tree, or the deep run handing back an old slice --
`parse_folder(channel, song_type)` is called with no `extra_info` at all, so the retag is
blind: whatever the first pass did not write into the tag was unrecoverable, because
nothing kept the dict.

Since migrate_v21 the archive row keeps a pruned copy of it
(`services/downloader/info_json.py`). This reads that copy back, so a retag sees what the
download saw. It decides nothing on its own: the caller hands the dict to the same
`BaseSong._apply_extra_info` the download path uses, which fills a tag only when it is
empty -- the one exception being GENRE, which is added and then judged by
`ResolveGenreRule` like any other inferred genre.

Matched on the absolute path the archive recorded, which is the only key both sides hold:
the tagger walks the filesystem and never learns a video id. A file moved or renamed since
its download therefore finds nothing and is tagged exactly as it is today. There is
deliberately no basename fallback -- two channels holding a file of the same name would
silently swap metadata, which is worse than having none.

Best effort throughout. An unreachable database or an unreadable blob means a round tags
without the extra info; it never means the round stops.
"""

import json
import logging

from services.common.Helpers.DatabaseConnector import DatabaseConnector
from services.tagger.constants import SongTypeEnum

#: One statement per source, written out rather than built with an f-string: there is
#: nothing to interpolate, and a formatted SQL string is a shape `security:sast` flags on
#: sight. The two archive tables disagree about which column holds the absolute path --
#: SoundCloud writes it to `filename`, YouTube to `path` -- so that difference lives here
#: instead of at the call site.
QUERY_BY_SOURCE = {
    SongTypeEnum.SOUNDCLOUD: (
        'SELECT info_json FROM downloads_soundcloud_archive WHERE filename = %s AND info_json IS NOT NULL LIMIT 1'
    ),
    SongTypeEnum.YOUTUBE: (
        'SELECT info_json FROM downloads_youtube_archive WHERE path = %s AND info_json IS NOT NULL LIMIT 1'
    ),
}


def stored_info(path, song_type) -> dict | None:
    """The info dict recorded for `path`, or None when there is not one.

    None is the answer for every song type that has no archive table, and it costs no
    query to say so: this runs once per file in a tagging round, and the label tree is
    two thirds of the library.
    """
    query = QUERY_BY_SOURCE.get(song_type)
    if not query:
        return None
    try:
        with DatabaseConnector().connection() as conn, conn.cursor() as cursor:
            cursor.execute(query, (str(path),))
            row = cursor.fetchone()
    except Exception as e:
        logging.debug('Could not read the download info of %s: %s', path, e)
        return None
    if not row or not row[0]:
        return None
    try:
        info = json.loads(row[0])
    except (TypeError, ValueError) as e:
        # Worth a warning rather than a debug line: the blob was written by this codebase,
        # so unreadable JSON means the pruning wrote something malformed, not that an
        # extractor sent something odd.
        logging.warning('The stored download info of %s is not readable JSON: %s', path, e)
        return None
    return info if isinstance(info, dict) else None
