import logging

from data.DatabaseConnector import DatabaseConnector


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