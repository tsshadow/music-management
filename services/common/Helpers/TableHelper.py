import logging
import time
from contextlib import closing
from threading import RLock

from services.common.Helpers.DatabaseConnector import DatabaseConnector


class TableHelper:
    """One column of one table, held in memory.

    Every read is served from the cache when `preload` is on. The cache is replaced, never
    mutated: a refresh builds the new set and map and publishes both in one assignment, and
    `add`/`delete` do the same, so anything a caller was handed keeps being a consistent
    snapshot while 16 tagger threads share the helper. The lock only serializes the
    publish and the refresh check.
    """

    #: How long a cached table is trusted before the next read re-reads it. The process that
    #: writes a value calls `reload` and is correct at once; the importer and downloader
    #: containers only learn of a new artist through this. `library_artists` is 57k rows and
    #: a full read takes about half a second, so once a minute is noise -- and the
    #: alternative, reading it per file, is what cost the tagger 1.6 s of every 2.2 s.
    STALE_AFTER_SECONDS = 60

    def __init__(self, table_name: str, column_name: str, preload: bool = True):
        self.table_name = table_name
        self.column_name = column_name
        self.db_connector = DatabaseConnector()
        self.cache_enabled = preload
        self._lock = RLock()
        self._loaded_at = float('-inf')
        self._values: frozenset[str] = frozenset()
        self._canonical_map: dict[str, str] = {}
        if preload:
            self._preload()

    def _preload(self):
        """Read the table and publish it as one snapshot; keep the old one on failure."""
        query = f'SELECT {self.column_name} FROM {self.table_name}'
        with self._lock:
            # Stamped before the query, as LookupTableHelper does: a database that is down
            # must not turn every lookup into a reconnect attempt.
            self._loaded_at = time.monotonic()
            try:
                with closing(self.db_connector.connect()) as connection, connection.cursor() as cursor:
                    cursor.execute(query)
                    rows = [row[0] for row in cursor.fetchall() if row and row[0] is not None]
                self._publish(frozenset(rows), {value.lower(): value for value in rows})
            except Exception as e:
                logging.error(f'Error preloading {self.table_name}: {e}')

    def _publish(self, values: frozenset[str], canonical: dict[str, str]):
        self._values = values
        self._canonical_map = canonical

    def _refresh_if_stale(self):
        if time.monotonic() - self._loaded_at >= self.STALE_AFTER_SECONDS:
            self._preload()

    def reload(self):
        """Re-read the table, e.g. after a rule was changed in the web UI.

        The tagger runs as a long-lived loop, so without this a value added today
        would first take effect after the next container restart. See
        LookupTableHelper.reload for the same reasoning.
        """
        if not self.cache_enabled:
            return
        self._preload()

    def exists(self, key: str) -> bool:
        """Whether `key` is in the table."""
        if self.cache_enabled:
            with self._lock:
                self._refresh_if_stale()
                return key.lower() in self._canonical_map
        query = f'SELECT 1 FROM {self.table_name} WHERE {self.column_name} = %s LIMIT 1'
        try:
            with closing(self.db_connector.connect()) as connection, connection.cursor() as cursor:
                cursor.execute(query, (key,))
                return cursor.fetchone() is not None
        except Exception as e:
            logging.error(f'Error checking existence in {self.table_name}: {e}')
            return False

    def get(self, key: str) -> str:
        """The stored spelling of `key`, looked up case-insensitively, or '' when absent."""
        if self.cache_enabled:
            with self._lock:
                self._refresh_if_stale()
                return str(self._canonical_map.get(key.lower(), ''))
        query = f'SELECT {self.column_name} FROM {self.table_name} WHERE LOWER({self.column_name}) = %s LIMIT 1'
        try:
            with closing(self.db_connector.connect()) as connection, connection.cursor() as cursor:
                cursor.execute(query, (key.lower(),))
                result = cursor.fetchone()
                return result[0] if result else key.title()
        except Exception as e:
            logging.error(f'Error fetching canonical value from {self.table_name}: {e}')
            return key.title()

    def add(self, key: str) -> bool:
        """Insert `key` unless it is already there; True when the write succeeded."""
        query = f'INSERT INTO {self.table_name} ({self.column_name}) VALUES (%s) ON DUPLICATE KEY UPDATE {self.column_name} = VALUES({self.column_name})'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
            connection.commit()
        except Exception as e:
            logging.error(f'Error inserting into {self.table_name}: {e}')
            connection.rollback()
            return False
        finally:
            connection.close()
        # After the commit, not before: a failed insert used to leave the name in the cache,
        # and every rule that asked "is this an artist" was told yes for a row that did not exist.
        if self.cache_enabled:
            with self._lock:
                self._publish(self._values | {key}, {**self._canonical_map, key.lower(): key})
        return True

    def delete(self, key: str) -> bool:
        """Delete `key`; True when the write succeeded."""
        query = f'DELETE FROM {self.table_name} WHERE {self.column_name} = %s'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
            connection.commit()
        except Exception as e:
            logging.error(f'Error deleting from {self.table_name}: {e}')
            connection.rollback()
            return False
        finally:
            connection.close()
        if self.cache_enabled:
            with self._lock:
                self._publish(
                    frozenset(v for v in self._values if v.lower() != key.lower()),
                    {k: v for k, v in self._canonical_map.items() if k != key.lower()},
                )
        return True

    def get_all_values(self) -> list[str]:
        """Every value in the column. From the cache when there is one -- this used to go to
        the database every time, and the artist rules call it three times per file."""
        if self.cache_enabled:
            with self._lock:
                self._refresh_if_stale()
                return list(self._values)
        query = f'SELECT {self.column_name} FROM {self.table_name}'
        try:
            with closing(self.db_connector.connect()) as connection, connection.cursor() as cursor:
                cursor.execute(query)
                return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f'Error retrieving values from {self.table_name}: {e}')
            return []

    def lowercase_map(self) -> dict[str, str]:
        """lower-cased value -> value as stored, the index the artist rules build per file.

        The returned dict is a snapshot that is never mutated afterwards (see the class
        docstring), so callers may read it without the lock. Only meaningful with a cache;
        without one it is built from a fresh read.
        """
        if self.cache_enabled:
            with self._lock:
                self._refresh_if_stale()
                return self._canonical_map
        return {value.lower(): value for value in self.get_all_values() if value}
