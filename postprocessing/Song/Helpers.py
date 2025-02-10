import logging

from data.DatabaseConnector import DatabaseConnector

'''
Helper class which wraps a table with a key:value setup
for example Artist->Genre
'''
class LookupTableHelper:
    def __init__(self, table_name, key_column_name, value_column_name):
        self.table_name = table_name
        self.key_column_name = key_column_name
        self.value_column_name = value_column_name
        self.db_connector = DatabaseConnector()

    def get(self, key) -> list[str]:
        query = f"SELECT {self.value_column_name} FROM {self.table_name} WHERE {self.key_column_name} = %s"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, key)
                result = cursor.fetchall()
                if result:
                    return [str(row[0]) for row in result]
                else:
                    return []
        except Exception as e:
            logging.error(f"Error querying database: {e}")
            return []


'''
Helper class which wraps a table with a single column setup.

This can be used to only allow filtered values. (For example genres)
'''
class FilterTableHelper:
    def __init__(self, table_name, column_name, corrected_column_name):
        self.table_name = table_name
        self.column_name = column_name
        self.corrected_column_name = corrected_column_name
        self.db_connector = DatabaseConnector()

    def exists(self, key) -> bool:
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

    def get_corrected(self, key) -> str:
        query = f"SELECT {self.corrected_column_name} FROM {self.table_name} WHERE {self.column_name} = %s LIMIT 1"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                result = cursor.fetchone()
                return result[0]
        except Exception as e:
            logging.error(f"Error querying database: {e}")
            return ""

    def add(self, key: str) -> bool:
        query = f"INSERT INTO {self.table_name} ({self.column_name}) VALUES (%s)"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (key,))
                connection.commit()  # Commit the transaction to save the insert
                return True
        except Exception as e:
            logging.error(f"Error inserting into database: {e}")
            connection.rollback()  # Rollback in case of an error
            return False
        finally:
            connection.close()

