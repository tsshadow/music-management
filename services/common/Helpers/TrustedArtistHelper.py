"""The artist names the tagger may trust: what its artist rules match titles against.

Until this existed, the tagger's artist dictionary was `library_artists` itself, and the
scanner inserts every artist string it finds in a file. A name a tagger rule *guessed*
out of a title therefore became a known artist one scan later, and from then on
`InferArtistFromTitleRule` picked it out of every title it appeared in -- the guess
approved itself (see docs/designs/artist-curation/technical.md, "Wiring the queue").

A name is trusted when

* a curator approved it: a `white` row in `rules_artists` (a person, or the
  `auto-external` evidence run of tools/artist_auto_approve.py), or
* it was already in `library_artists` when the queue was wired up and nobody has
  decided on it since: a row in `rules_artist_legacy_trust`, seeded once by
  migrate_v40. Those names were trusted before, and taking them away would change what
  every retag of the existing library produces.

Everything else in `library_artists` is *pending*: it stays in the files that carry it,
it is listed in the curation queue, and no tagger rule matches it until it is approved.
A rejected name (`black`) is never trusted -- which is also what lets CheckArtistRule
reach its correction branch for a name the scanner had already inserted.

The helper keeps the registry key and the table name `library_artists`, so every rule
that took `databaseHelpers['library_artists']` gets the trusted set without a change,
and a caching `TableHelper` it still is: the rules' snapshot tracking
(`lowercase_map` identity) works unchanged.
"""

from __future__ import annotations

import logging
import time
from contextlib import closing

from services.common.Helpers.TableHelper import TableHelper

#: The trusted names, grandfathered ones first and approved ones last: the map built from
#: the rows keeps the last spelling per lower-cased name, so an approved spelling wins
#: over a legacy variant that differs only in casing.
TRUSTED_ARTISTS_SQL = """
    SELECT a.name, 0 AS rank_order
    FROM library_artists a
    JOIN rules_artist_legacy_trust l ON l.name = a.name
    LEFT JOIN rules_artists r ON r.name = a.name
    WHERE r.name IS NULL
    UNION ALL
    SELECT r.name, 1 AS rank_order
    FROM rules_artists r
    WHERE r.state = 'white'
    ORDER BY rank_order
"""

#: Who an approval made at the tagger's interactive prompt is recorded as.
PROMPT_DECIDER = 'tagger-prompt'


class TrustedArtistHelper(TableHelper):
    """`library_artists` as the tagger sees it: approved and grandfathered names only."""

    def __init__(self, preload: bool = True):
        # Always cached: the uncached TableHelper paths query `library_artists` directly,
        # which is exactly the untrusted set this class exists to hide.
        super().__init__('library_artists', 'name', preload=False)
        self.cache_enabled = True
        if preload:
            self._preload()

    def _preload(self):
        """Read the trusted names and publish them as one snapshot; keep the old one on failure."""
        with self._lock:
            self._loaded_at = time.monotonic()
            try:
                with closing(self.db_connector.connect()) as connection, connection.cursor() as cursor:
                    cursor.execute(TRUSTED_ARTISTS_SQL)
                    rows = [row[0] for row in cursor.fetchall() if row and row[0] is not None]
                self._publish(frozenset(rows), {value.lower(): value for value in rows})
            except Exception as e:
                logging.error(f'Error preloading trusted artists: {e}')

    def add(self, key: str) -> bool:
        """Approve `key`: the interactive prompt's "yes, this is an artist".

        Written as a curation decision, not a bare library row -- a bare row is exactly
        what no longer counts as trust.
        """
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute('INSERT IGNORE INTO library_artists (name) VALUES (%s)', (key,))
                cursor.execute(
                    'INSERT INTO rules_artists (name, state, decided_by) VALUES (%s, %s, %s) '
                    'ON DUPLICATE KEY UPDATE state = VALUES(state), canonical_name = NULL, '
                    'decided_at = NOW(), decided_by = VALUES(decided_by)',
                    (key, 'white', PROMPT_DECIDER),
                )
            connection.commit()
        except Exception as e:
            logging.error(f'Error approving artist {key}: {e}')
            connection.rollback()
            return False
        finally:
            connection.close()
        with self._lock:
            self._publish(self._values | {key}, {**self._canonical_map, key.lower(): key})
        return True
