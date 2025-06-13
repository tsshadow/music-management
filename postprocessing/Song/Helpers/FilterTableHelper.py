import logging
from data.DatabaseConnector import DatabaseConnector


class FilterTableHelper:
    """
    Helper class for interacting with a database table that acts as a filter
    or whitelist for allowed values (e.g., genres, tag vocabularies).

    This wrapper assumes the table contains at least:
    - One main column for lookup (e.g. 'name').
    - One optional corrected version column (e.g. 'standardized_name').
    """

    def __init__(self, table_name: str, column_name: str, corrected_column_name: str):
        """
        Initializes the filter helper with the given table and column names.

        Args:
            table_name (str): Name of the table to query/insert into.
            column_name (str): Name of the column used for lookup and inserts.
            corrected_column_name (str): Name of the column to retrieve corrected values from.
        """
        self.table_name = table_name
        self.column_name = column_name
        self.corrected_column_name = corrected_column_name
        self.db_connector = DatabaseConnector()

    def exists(self, key: str) -> bool:
        """
        Checks whether the given key exists in the filter table.

        Args:
            key (str): The value to check.

        Returns:
            bool: True if the key exists in the table, False otherwise.
        """
        query = f"SELECT 1 FROM {self.table_name} WHERE {self.column_name} = %s LIMIT 1"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchone()
                return result is not None
        except Exception as e:
            logging.error(f"Error querying database: {e}")
            return False

    def get_corrected(self, key: str) -> str:
        """
        Retrieves the corrected value for a given key from the table.

        Args:
            key (str): The value to correct.

        Returns:
            str: The corrected version of the key, or an empty string if not found.
        """
        query = f"SELECT {self.corrected_column_name} FROM {self.table_name} WHERE {self.column_name} = %s LIMIT 1"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchone()
                return result[0] if result else ""
        except Exception as e:
            logging.error(f"Error querying database: {e}")
            return ""

    def get_corrected_or_exists(self, key: str) -> str | bool:
        """
        Returns the corrected value if one exists for the given key.
        If not corrected but exists, returns the original key.
        If neither corrected nor existing, returns False.

        Args:
            key (str): The value to check and possibly correct.

        Returns:
            str | bool: Corrected value, original key, or False.
        """
        query = f"""
            SELECT {self.corrected_column_name}
            FROM {self.table_name}
            WHERE {self.column_name} = %s
            LIMIT 1
        """
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchone()
                if result:
                    corrected = result[0]
                    return corrected if corrected else key
                return False
        except Exception as e:
            logging.error(f"Error querying database: {e}")
            return False


    def add(self, key: str, corrected: str | None = None) -> bool:
        """
        Inserts a new key into the filter table.

        Args:
            key (str): The value to insert.
            corrected (str | None): Optional corrected value.

        Returns:
            bool: True if the insert succeeded, False otherwise.
        """
        columns = [self.column_name]
        values = [key]

        # Voeg alleen toe als de kolom ook daadwerkelijk bestaat
        if self.corrected_column_name and corrected is not None:
            columns.append(self.corrected_column_name)
            values.append(corrected)

        placeholders = ', '.join(['%s'] * len(columns))
        column_names = ', '.join(columns)
        query = f"INSERT INTO {self.table_name} ({column_names}) VALUES ({placeholders})"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, values)
                connection.commit()
                return True
        except Exception as e:
            logging.error(f"Error inserting into database: {e}")
            connection.rollback()
            return False
        finally:
            connection.close()
