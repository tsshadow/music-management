import logging
from contextlib import closing
from typing import List
from data.DatabaseConnector import DatabaseConnector

class TableHelper:
    def __init__(self, table_name: str, column_name: str):
        self.table_name = table_name
        self.column_name = column_name
        self.db_connector = DatabaseConnector()

    def exists(self, key: str) -> bool:
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
