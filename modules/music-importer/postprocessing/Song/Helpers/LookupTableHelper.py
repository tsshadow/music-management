import logging
from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


class LookupTableHelper:
    """
        Helper class for accessing a key-value mapping table in a database.

        Suitable for cases like Artist → Genre or Label → Country, where each
        key may map to one or more values.

        The table is expected to contain:
        - A key column (e.g. 'artist')
        - A value column (e.g. 'genre')
        """

    def __init__(self, table_name: str, key_column_name: str, value_column_name: str, preload: bool = True):
        self.table_name = table_name
        self.key_column_name = key_column_name
        self.value_column_name = value_column_name
        self.db_connector = DatabaseConnector()
        self.cache_enabled = preload

        self._kv_map = {}

        if preload:
            self._preload()

    def _preload(self):
        query = f"SELECT {self.key_column_name}, {self.value_column_name} FROM {self.table_name}"
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error(f"[{self.table_name}] Failed to preload key-value pairs: {e}")
            return

        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                for key, value in cursor.fetchall():
                    if key is None or value is None:
                        continue
                    key = str(key).strip()
                    value = str(value).strip()
                    self._kv_map.setdefault(key, []).append(value)
        except Exception as e:
            logging.error(f"[{self.table_name}] Failed to preload key-value pairs: {e}")
        finally:
            connection.close()

    def get(self, key: str) -> list[str]:
        key = key.strip()
        if self.cache_enabled:
            key_lower = key.lower()
            for existing_key, values in self._kv_map.items():
                if existing_key.lower() == key_lower:
                    return values
            return []

        # fallback to DB
        query = f"SELECT {self.value_column_name} FROM {self.table_name} WHERE LOWER({self.key_column_name}) = LOWER(%s)"
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
        if self.cache_enabled:
            matches = {
                value
                for key, values in self._kv_map.items()
                if key.lower() in input_lower
                for value in values
            }
            return sorted(matches)

        # fallback to DB
        query = f"SELECT {self.key_column_name}, {self.value_column_name} FROM {self.table_name}"
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error(f"[{self.table_name}] Failed to get substring matches for '{input_string}': {e}")
            return []
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchall()
                matches = {
                    str(value).strip()
                    for name, value in result
                    if name and name.lower().strip() in input_lower
                }
                return sorted(matches)
        except Exception as e:
            logging.error(f"[{self.table_name}] Failed to get substring matches for '{input_string}': {e}")
            return []
        finally:
            connection.close()
