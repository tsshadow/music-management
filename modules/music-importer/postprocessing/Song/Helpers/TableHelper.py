import logging
from contextlib import closing
from typing import List
from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector

class TableHelper:
    def __init__(self, table_name: str, column_name: str, preload: bool = True):
        self.table_name = table_name
        self.column_name = column_name
        self.db_connector = DatabaseConnector()
        self.cache_enabled = preload

        self._values = set()
        self._canonical_map = {}

        if preload:
            self._preload()

    def _preload(self):
        """Load all values from the table into memory."""
        query = f"SELECT {self.column_name} FROM {self.table_name}"
        try:
            with closing(self.db_connector.connect()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    rows = cursor.fetchall()
                    for row in rows:
                        value = row[0]
                        self._values.add(value)
                        self._canonical_map[value.lower()] = value
        except Exception as e:
            logging.error(f"Error preloading {self.table_name}: {e}")

    def exists(self, key: str) -> bool:
        if self.cache_enabled:
            return key.lower() in (k.lower() for k in self._values)
        # fallback to DB
        query = f"SELECT 1 FROM {self.table_name} WHERE {self.column_name} = %s LIMIT 1"
        try:
            with closing(self.db_connector.connect()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, (key,))
                    return cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"Error checking existence in {self.table_name}: {e}")
            return False

    def get(self, key: str) -> str:
        if self.cache_enabled:
            return self._canonical_map.get(key.lower(), "")
        # fallback to DB
        query = f"SELECT {self.column_name} FROM {self.table_name} WHERE LOWER({self.column_name}) = %s LIMIT 1"
        try:
            with closing(self.db_connector.connect()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query, (key.lower(),))
                    result = cursor.fetchone()
                    return result[0] if result else key.title()
        except Exception as e:
            logging.error(f"Error fetching canonical value from {self.table_name}: {e}")
            return key.title()

    def add(self, key: str) -> bool:
        # Update cache if enabled
        if self.cache_enabled:
            self._values.add(key)
            self._canonical_map[key.lower()] = key
        query = f"INSERT INTO {self.table_name} ({self.column_name}) VALUES (%s)"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
            connection.commit()
            return True
        except Exception as e:
            logging.error(f"Error inserting into {self.table_name}: {e}")
            connection.rollback()  # <== this line should execute
            return False
        finally:
            connection.close()

    def get_all_values(self) -> List[str]:
        query = f"SELECT {self.column_name} FROM {self.table_name}"
        try:
            with closing(self.db_connector.connect()) as connection:
                with connection.cursor() as cursor:
                    cursor.execute(query)
                    return [row[0] for row in cursor.fetchall()]
        except Exception as e:
            logging.error(f"Error retrieving values from {self.table_name}: {e}")
            return []
