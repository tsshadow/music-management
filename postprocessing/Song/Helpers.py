import logging
from typing import Optional
import re

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

    def get_substring(self, input_string: str) -> list[str]:
        query = f"SELECT {self.key_column_name}, {self.value_column_name} FROM {self.table_name}"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                result = cursor.fetchall()
                matches = []
                for name, value in result:
                    if name.lower() in input_string.lower():
                        matches.append(str(value))
                return matches
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

class FestivalHelper:
    def __init__(self, table_name="festival_data"):
        self.table_name = table_name
        self.db_connector = DatabaseConnector()

    def get(self, input_string: str) -> Optional[dict]:
        """
        Parses input string (e.g. filename) to detect festival and year.
        Returns a dictionary with festival, year, and date.
        """
        year = self._extract_year(input_string)
        if not year:
            logging.debug("No year found in input.")
            return None

        # Fetch all possible festivals for that year
        query = f"""
            SELECT festival, date FROM {self.table_name}
            WHERE year = %s
        """
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (year,))
                rows = cursor.fetchall()
                matches = []

                for festival, date in rows:
                    if festival.lower() in input_string.lower():
                        matches.append((festival, date))

                if not matches:
                    logging.debug("No matching festival found in input string.")
                    return None

                # Prefer longest (most specific) match
                matches.sort(key=lambda x: len(x[0]), reverse=True)
                best_match = matches[0]

                return {
                    "festival": best_match[0],
                    "year": year,
                    "date": best_match[1].isoformat()
                }

        except Exception as e:
            logging.error(f"Error querying database: {e}")
            return None

    def _extract_year(self, text: str) -> Optional[int]:
        match = re.search(r"\b(20\d{2})\b", text)
        return int(match.group(1)) if match else None
