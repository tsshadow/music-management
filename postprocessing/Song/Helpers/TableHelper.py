import logging
from data.DatabaseConnector import DatabaseConnector


class TableHelper:
    """
    Helper for working with a simple key-based database table (e.g. genres, artists).
    Supports checking if a value exists, adding values, and getting canonical capitalization.
    """

    def __init__(self, table_name: str, column_name: str):
        self.table_name = table_name
        self.column_name = column_name
        self.db_connector = DatabaseConnector()

    def exists(self, key: str) -> bool:
        """
        Checks if the exact value exists in the table.

        Args:
            key (str): The value to check.

        Returns:
            bool: True if found.
        """
        query = f"SELECT 1 FROM {self.table_name} WHERE {self.column_name} = %s LIMIT 1"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                return cursor.fetchone() is not None
        except Exception as e:
            logging.error(f"Error checking existence in {self.table_name}: {e}")
            return False

    def get_canonical(self, key: str) -> str:
        """
        Retrieves the stored capitalization of a key, case-insensitively.
        Falls back to title-cased version if not found.

        Args:
            key (str): Input value.

        Returns:
            str: Canonical value from DB or fallback.
        """
        query = f"SELECT {self.column_name} FROM {self.table_name} WHERE LOWER({self.column_name}) = %s LIMIT 1"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key.lower(),))
                result = cursor.fetchone()
                return result[0] if result else key.title()
        except Exception as e:
            logging.error(f"Error fetching canonical value from {self.table_name}: {e}")
            return key.title()

    def add(self, key: str) -> bool:
        """
        Inserts a new value into the table.

        Args:
            key (str): Value to insert.

        Returns:
            bool: True if successful.
        """
        query = f"INSERT INTO {self.table_name} ({self.column_name}) VALUES (%s)"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                connection.commit()
                return True
        except Exception as e:
            logging.error(f"Error inserting into {self.table_name}: {e}")
            connection.rollback()
            return False
        finally:
            connection.close()
