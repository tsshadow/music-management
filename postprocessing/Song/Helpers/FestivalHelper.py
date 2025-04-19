import logging
from typing import Optional
import re

from data.DatabaseConnector import DatabaseConnector


class FestivalHelper:
    """
    Helper class to identify festivals and their corresponding years/dates
    based on a string input (typically filenames or folder names).
    Looks up results from a SQL table, defaulting to 'festival_data'.
    """

    def __init__(self, table_name="festival_data"):
        """
        Initializes the FestivalHelper with a given database table name.

        Args:
            table_name (str): The name of the database table containing festival info.
        """
        self.table_name = table_name
        self.db_connector = DatabaseConnector()

    def get(self, input_string: str) -> Optional[dict]:
        """
        Attempts to identify a festival and year from a given input string
        and returns structured festival information.

        The method:
        - Extracts the year from the input string using regex.
        - Queries all festivals for that year.
        - Finds any that match substrings within the input string.
        - Returns the most specific match (longest name) if found.

        Args:
            input_string (str): A filename, folder name, or general string to parse.

        Returns:
            dict or None: A dictionary with keys `festival`, `year`, and `date` (ISO format),
                          or None if no match is found.
        """
        year = self._extract_year(input_string)
        if not year:
            logging.debug("No year found in input.")
            return None

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
        """
        Extracts a 4-digit year (starting with 20xx) from the input string.

        Args:
            text (str): Text to search for a year.

        Returns:
            int or None: The extracted year, or None if not found.
        """
        match = re.search(r"\b(20\d{2})\b", text)
        return int(match.group(1)) if match else None
