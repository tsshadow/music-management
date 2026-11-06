"""Which label and artist the channel a file came through is linked to.

A curator links a SoundCloud or YouTube channel to its label or artist in Management > Downloaders ->
Links (docs/designs/channel-links). The tagger reads that link here, per file, to fill the
publisher and replace an artist that is only the channel's own name standing in for one.

The file is placed under its channel by the same two functions the scanner uses to fill
`library_track_channels` (`channel_from_path` and `normalize_channel_name`), so the tagger and the
library can never disagree about which channel a file belongs to.

Linked channels are a few hundred rows at most, so the whole set is held in memory and rebuilt
on `reload()` -- which `Tagger.run` calls before each round and the channel-links router calls
after every link change -- or after `STALE_AFTER_SECONDS`, which is how the downloader and
importer processes catch up on a link made in the music-manager process.
"""

from __future__ import annotations

import logging
import time
from collections.abc import Iterable
from dataclasses import dataclass

from services.common.channels import channel_from_path, normalize_channel_name
from services.common.Helpers.DatabaseConnector import DatabaseConnector

#: Every linked channel with the names it is linked to. The artist half is only filled while
#: that artist is still approved: a link to an artist rejected after the link was made is
#: ignored rather than written into files, which is what artist curation asks of every name
#: the tagger writes.
LINKS_SQL = """
    SELECT c.platform, c.normalized_name, l.name AS label_name,
           CASE WHEN EXISTS (
               SELECT 1 FROM rules_artists r WHERE r.name = a.name AND r.state = 'white'
           ) THEN a.name END AS artist_name
    FROM channels c
    LEFT JOIN library_labels l ON l.id = c.label_id
    LEFT JOIN library_artists a ON a.id = c.artist_id
    WHERE c.label_id IS NOT NULL OR c.artist_id IS NOT NULL
"""


@dataclass(frozen=True)
class ChannelLink:
    """The label and artist one channel is linked to; either may be None."""

    label: str | None = None
    artist: str | None = None


class ChannelLinkHelper:
    """In-memory map from (platform, channel key) to the channel's link."""

    #: Same trade as LookupTableHelper: a minute of lag on a link made in another process.
    STALE_AFTER_SECONDS = 60

    def __init__(self, preload: bool = True):
        self.db_connector = DatabaseConnector()
        self.cache_enabled = preload
        self._links: dict[tuple[str, str], ChannelLink] = {}
        self._loaded_at = 0.0
        if preload:
            self._preload()

    def reload(self) -> None:
        """Rebuild the map from the database, now."""
        if self.cache_enabled:
            self._preload()

    def set_links(self, rows: Iterable[tuple[str, str, str | None, str | None]]) -> None:
        """Replace the map with `(platform, channel name, label, artist)` rows. For tests."""
        self._links = self._index(rows)

    def link_for(self, path: str | None) -> ChannelLink | None:
        """The link of the channel `path` lies under, or None when it has none (or no channel)."""
        found = channel_from_path(path or '')
        if not found:
            return None
        self._refresh_if_stale()
        platform, name = found
        return self._links.get((platform, normalize_channel_name(name)))

    @staticmethod
    def _index(rows) -> dict[tuple[str, str], ChannelLink]:
        links = {}
        for platform, name, label, artist in rows:
            link = ChannelLink(label=(label or '').strip() or None, artist=(artist or '').strip() or None)
            if link.label or link.artist:
                links[(str(platform), normalize_channel_name(str(name or '')))] = link
        return links

    def _refresh_if_stale(self) -> None:
        if not self.cache_enabled:
            return
        if time.monotonic() - self._loaded_at < self.STALE_AFTER_SECONDS:
            return
        self._preload()

    def _preload(self) -> None:
        # Stamped before the query, as in LookupTableHelper: a database that is down must not
        # turn every file of a round into a reconnect attempt.
        self._loaded_at = time.monotonic()
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error(f'[channel links] Failed to load: {e}')
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute(LINKS_SQL)
                rows = cursor.fetchall()
        except Exception as e:
            # The previous map stays: slightly stale links beat no links at all.
            logging.error(f'[channel links] Failed to load: {e}')
            return
        finally:
            connection.close()
        self._links = self._index(self._as_tuple(row) for row in rows)

    @staticmethod
    def _as_tuple(row) -> tuple:
        """A row from either a tuple or a dict cursor."""
        if isinstance(row, dict):
            return (row['platform'], row['normalized_name'], row['label_name'], row['artist_name'])
        return tuple(row)
