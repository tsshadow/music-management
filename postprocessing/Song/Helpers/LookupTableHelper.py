import logging
from data.DatabaseConnector import DatabaseConnector


class LookupTableHelper:
    """
    Helper class for accessing a key-value mapping table in a database.

    Suitable for cases like Artist → Genre or Label → Country, where each
    key may map to one or more values.

    The table is expected to contain:
    - A key column (e.g. 'artist')
    - A value column (e.g. 'genre')
    """

    def __init__(self, table_name: str, key_column_name: str, value_column_name: str):
        """
        Initializes the lookup helper with the given table and column names.

        Args:
            table_name (str): The name of the database table.
            key_column_name (str): The name of the column representing the keys.
            value_column_name (str): The name of the column representing the values.
        """
        self.table_name = table_name
        self.key_column_name = key_column_name
        self.value_column_name = value_column_name
        self.db_connector = DatabaseConnector()

    def get(self, key: str) -> list[str]:
        """
        Retrieves all values associated with the given key.

        Args:
            key (str): The key to look up.

        Returns:
            list[str]: A list of matching values, or an empty list if none found.
        """
        query = f"SELECT {self.value_column_name} FROM {self.table_name} WHERE {self.key_column_name} = %s"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchall()
                return [str(row[0]) for row in result] if result else []
        except Exception as e:
            logging.error(f"Error querying database: {e}")
            return []

    def get_substring(self, input_string: str) -> list[str]:
        """
        Retrieves values for any key that is a substring match (case-insensitive)
        within the input string.

        This is useful for fuzzy lookup based on filenames or folder names.

        Args:
            input_string (str): Text to scan for known keys.

        Returns:
            list[str]: Values for all matching keys found in the string.
        """
        query = f"SELECT {self.key_column_name}, {self.value_column_name} FROM {self.table_name}"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchall()
                matches = [
                    str(value)
                    for name, value in result
                    if name.lower() in input_string.lower()
                ]
                return matches
        except Exception as e:
            logging.error(f"Error querying database: {e}")
            return []
