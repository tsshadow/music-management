import logging
from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


class FilterTableHelper:
    def __init__(self, table_name: str, column_name: str, corrected_column_name: str, preload: bool = True):
        self.table_name = table_name
        self.column_name = column_name
        self.corrected_column_name = corrected_column_name
        self.db_connector = DatabaseConnector()
        self.cache_enabled = preload

        self._exists_cache = set()
        self._corrected_map = {}

        if preload:
            self._preload()

    def _preload(self):
        query = f"SELECT {self.column_name}, {self.corrected_column_name} FROM {self.table_name}"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                for row in cursor.fetchall():
                    name = str(row[0]).strip()
                    corrected = str(row[1]).strip() if row[1] else ""
                    self._exists_cache.add(name)
                    if corrected:
                        self._corrected_map[name] = corrected
        except Exception as e:
            logging.error(f"[{self.table_name}] Error preloading table: {e}")
        finally:
            connection.close()

    def exists(self, key: str) -> bool:
        key = key.strip()
        if self.cache_enabled:
            return key.lower() in (k.lower() for k in self._exists_cache)

        query = f"SELECT 1 FROM {self.table_name} WHERE {self.column_name} = %s LIMIT 1"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                return cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"[{self.table_name}] Error checking existence for key '{key}': {e}")
            return False
        finally:
            connection.close()

    def get_corrected(self, key: str) -> str:
        key = key.strip()
        if self.cache_enabled:
            return self._corrected_map.get(key, "")

        query = (
            f"SELECT {self.corrected_column_name} "
            f"FROM {self.table_name} WHERE {self.column_name} = %s LIMIT 1"
        )
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchone()
                return result[0].strip() if result and result[0] else ""
        except Exception as e:
            logging.error(f"[{self.table_name}] Error fetching corrected value for '{key}': {e}")
            return ""
        finally:
            connection.close()

    def get_corrected_or_exists(self, key: str) -> str | bool:
        key = key.strip()
        if self.cache_enabled:
            if key in self._corrected_map:
                return self._corrected_map[key]
            elif key in self._exists_cache:
                return key
            else:
                return False

        # fallback to DB mode
        query = (
            f"SELECT {self.corrected_column_name} "
            f"FROM {self.table_name} WHERE {self.column_name} = %s LIMIT 1"
        )
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchone()
                if result:
                    corrected = result[0]
                    return corrected.strip() if corrected else key
                return False
        except Exception as e:
            logging.error(f"[{self.table_name}] Error fetching corrected/existing for '{key}': {e}")
            return False
        finally:
            connection.close()

    def add(self, key: str, corrected: str | None = None) -> bool:
        key = key.strip()
        values = [key]
        columns = [self.column_name]

        if self.corrected_column_name and corrected is not None:
            corrected = corrected.strip()
            columns.append(self.corrected_column_name)
            values.append(corrected)

        placeholders = ", ".join(["%s"] * len(columns))
        column_names = ", ".join(columns)
        query = f"INSERT INTO {self.table_name} ({column_names}) VALUES ({placeholders})"

        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, values)
                connection.commit()
                return True
        except Exception as e:
            logging.error(f"[{self.table_name}] Error inserting key '{key}': {e}")
            connection.rollback()
            return False
        finally:
            connection.close()

    def get_all(self) -> list[str]:
        """
        Returns all raw (unprocessed) values from the main column.

        Returns:
            list[str]: Sorted list of distinct values.
        """
        query = f"SELECT DISTINCT {self.column_name} FROM {self.table_name}"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchall()
                return sorted([str(row[0]).strip() for row in result if row and row[0]])
        except Exception as e:
            logging.error(f"[{self.table_name}] Error fetching all values: {e}")
            return []
        finally:
            connection.close()
