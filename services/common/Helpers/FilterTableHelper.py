import logging

from services.common.Helpers.DatabaseConnector import DatabaseConnector


class FilterTableHelper:
    """Looks a value up in a rules table, case-insensitively.

    The values arrive from outside (SoundCloud genres, uploader tags), so the
    casing is whatever someone typed. Matching on the stored spelling alone
    would reject `Uptempo` while accepting `uptempo`, so every lookup here
    normalises to lowercase and answers with the *stored* spelling -- or with
    the correction, when the table defines one. That keeps one genre from
    entering the library under three different casings.
    """

    def __init__(self, table_name: str, column_name: str, corrected_column_name: str, preload: bool=True):
        self.table_name = table_name
        self.column_name = column_name
        self.corrected_column_name = corrected_column_name
        self.db_connector = DatabaseConnector()
        self.cache_enabled = preload
        self._exists_cache: set[str] = set()
        self._canonical_map: dict[str, str] = {}
        self._corrected_map: dict[str, str] = {}
        if preload:
            self._preload()

    def _preload(self):
        query = f'SELECT {self.column_name}, {self.corrected_column_name} FROM {self.table_name}'
        try:
            connection = self.db_connector.connect()
        except Exception as e:
            logging.error(f'[{self.table_name}] Error preloading table: {e}')
            return
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                for row in cursor.fetchall():
                    name = str(row[0]).strip()
                    corrected = str(row[1]).strip() if row[1] else ''
                    self._exists_cache.add(name)
                    self._canonical_map[name.lower()] = name
                    if corrected:
                        self._corrected_map[name.lower()] = corrected
        except Exception as e:
            logging.error(f'[{self.table_name}] Error preloading table: {e}')
        finally:
            connection.close()

    def reload(self):
        """Re-read the table. See LookupTableHelper.reload for why."""
        if not self.cache_enabled:
            return
        self._exists_cache = set()
        self._canonical_map = {}
        self._corrected_map = {}
        self._preload()

    def exists(self, key: str) -> bool:
        key = key.strip()
        if self.cache_enabled:
            return key.lower() in self._canonical_map
        query = f'SELECT 1 FROM {self.table_name} WHERE LOWER({self.column_name}) = LOWER(%s) LIMIT 1'
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
            return str(self._corrected_map.get(key.lower(), ''))
        query = f'SELECT {self.corrected_column_name} FROM {self.table_name} WHERE LOWER({self.column_name}) = LOWER(%s) LIMIT 1'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchone()
                return result[0].strip() if result and result[0] else ''
        except Exception as e:
            logging.error(f"[{self.table_name}] Error fetching corrected value for '{key}': {e}")
            return ''
        finally:
            connection.close()

    def get_corrected_or_exists(self, key: str) -> str | bool:
        """The correction for `key`, else its stored spelling, else False."""
        key = key.strip()
        normalized = key.lower()
        if self.cache_enabled:
            if normalized in self._corrected_map:
                return str(self._corrected_map[normalized])
            if normalized in self._canonical_map:
                return str(self._canonical_map[normalized])
            return False
        query = (f'SELECT {self.column_name}, {self.corrected_column_name} FROM {self.table_name} '
                 f'WHERE LOWER({self.column_name}) = LOWER(%s) LIMIT 1')
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchone()
                if result:
                    stored, corrected = result[0], result[1]
                    return corrected.strip() if corrected else str(stored).strip()
                return False
        except Exception as e:
            logging.error(f"[{self.table_name}] Error fetching corrected/existing for '{key}': {e}")
            return False
        finally:
            connection.close()

    def add(self, key: str, corrected: str | None=None) -> bool:
        key = key.strip()
        values = [key]
        columns = [self.column_name]
        if self.corrected_column_name and corrected is not None:
            corrected = corrected.strip()
            columns.append(self.corrected_column_name)
            values.append(corrected)
        placeholders = ', '.join(['%s'] * len(columns))
        column_names = ', '.join(columns)
        query = f'INSERT INTO {self.table_name} ({column_names}) VALUES ({placeholders})'
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

    def update(self, key: str, corrected: str | None=None) -> bool:
        """Set or clear the correction for an existing key.

        Matched case-insensitively, like every other lookup here: the stored spelling
        is whatever someone typed first and the caller should not have to reproduce it.
        """
        key = key.strip()
        corrected = corrected.strip() if corrected else None
        query = (f'UPDATE {self.table_name} SET {self.corrected_column_name} = %s '
                 f'WHERE LOWER({self.column_name}) = LOWER(%s)')
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (corrected, key))
                connection.commit()
                return True
        except Exception as e:
            logging.error(f"[{self.table_name}] Error updating key '{key}': {e}")
            connection.rollback()
            return False
        finally:
            connection.close()

    def delete(self, key: str) -> bool:
        """Remove the row for `key`, if there is one."""
        key = key.strip()
        query = f'DELETE FROM {self.table_name} WHERE LOWER({self.column_name}) = LOWER(%s)'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                connection.commit()
                return True
        except Exception as e:
            logging.error(f"[{self.table_name}] Error deleting key '{key}': {e}")
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
        query = f'SELECT DISTINCT {self.column_name} FROM {self.table_name}'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchall()
                return sorted([str(row[0]).strip() for row in result if row and row[0]])
        except Exception as e:
            logging.error(f'[{self.table_name}] Error fetching all values: {e}')
            return []
        finally:
            connection.close()