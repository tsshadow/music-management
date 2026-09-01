import logging
import time

from services.common.Helpers.DatabaseConnector import DatabaseConnector


class LookupTableHelper:
    """
    Helper class for accessing a key-value mapping table in a database.

    Suitable for cases like Artist → Genre or Label → Country, where each
    key may map to one or more values.

    The table is expected to contain:
    - A key column (e.g. 'artist')
    - A value column (e.g. 'genre')
    """

    #: How long a preloaded map is trusted before the next `get` rebuilds it.
    #:
    #: These tables are rules a human edits through the API, and `databaseHelpers`
    #: (Cache.py) builds every helper once at import, so without an expiry a new rule
    #: would stay invisible until the process restarts. The process that wrote the rule
    #: calls `reload` and is correct immediately; every *other* process that tags
    #: (importer, downloader) only finds out because of this interval. A minute of lag
    #: on a rule change is unnoticeable, and the tables are a few hundred rows, so the
    #: rebuild is far cheaper than the alternative of not caching at all.
    STALE_AFTER_SECONDS = 60

    def __init__(self, table_name: str, key_column_name: str, value_column_name: str, preload: bool = True):
        self.table_name = table_name
        self.key_column_name = key_column_name
        self.value_column_name = value_column_name
        self.db_connector = DatabaseConnector()
        self.cache_enabled = preload
        self._kv_map: dict[str, list[str]] = {}
        self._loaded_at = 0.0
        if preload:
            self._preload()

    def reload(self):
        """Rebuild the cached map from the database, now.

        Called by the API right after it writes a rule, so the answer the caller gets
        back already reflects what they just saved.
        """
        if not self.cache_enabled:
            return
        self._preload()

    def _refresh_if_stale(self):
        if not self.cache_enabled:
            return
        if time.monotonic() - self._loaded_at < self.STALE_AFTER_SECONDS:
            return
        self._preload()

    def _preload(self):
        query = f'SELECT {self.key_column_name}, {self.value_column_name} FROM {self.table_name}'
        # Stamped before the query rather than after it: a database that is down makes
        # `connect` raise on every call, and stamping only on success would turn that
        # into a reconnect attempt on literally every lookup.
        self._loaded_at = time.monotonic()
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error(f'[{self.table_name}] Failed to preload key-value pairs: {e}')
            return
        fresh: dict[str, list[str]] = {}
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                for key, value in cursor.fetchall():
                    if key is None or value is None:
                        continue
                    key = str(key).strip()
                    value = str(value).strip()
                    fresh.setdefault(key, []).append(value)
        except Exception as e:
            # The old map stays in place. A failed refresh should degrade to slightly
            # stale rules, never to no rules at all.
            logging.error(f'[{self.table_name}] Failed to preload key-value pairs: {e}')
            return
        finally:
            connection.close()
        self._kv_map = fresh

    def get(self, key: str) -> list[str]:
        key = key.strip()
        self._refresh_if_stale()
        if self.cache_enabled:
            key_lower = key.lower()
            for existing_key, values in self._kv_map.items():
                if existing_key.lower() == key_lower:
                    return list(values)
            return []
        query = (
            f'SELECT {self.value_column_name} FROM {self.table_name} WHERE LOWER({self.key_column_name}) = LOWER(%s)'
        )
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error(f"[{self.table_name}] Failed to get values for key '{key}': {e}")
            return []
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                return [str(row[0]).strip() for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"[{self.table_name}] Failed to get values for key '{key}': {e}")
            return []
        finally:
            connection.close()

    def get_substring(self, input_string: str) -> list[str]:
        input_lower = input_string.lower()
        self._refresh_if_stale()
        if self.cache_enabled:
            matches = {value for key, values in self._kv_map.items() if key.lower() in input_lower for value in values}
            return sorted(matches)
        query = f'SELECT {self.key_column_name}, {self.value_column_name} FROM {self.table_name}'
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error(f"[{self.table_name}] Failed to get substring matches for '{input_string}': {e}")
            return []
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchall()
                matches = {str(value).strip() for name, value in result if name and name.lower().strip() in input_lower}
                return sorted(matches)
        except Exception as e:
            logging.error(f"[{self.table_name}] Failed to get substring matches for '{input_string}': {e}")
            return []
        finally:
            connection.close()
