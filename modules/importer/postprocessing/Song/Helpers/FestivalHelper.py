import logging
import re
from typing import Optional

from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


class FestivalHelper:
    """
    Helper class to identify festivals and their corresponding years/dates
    based on a string input (typically filenames or folder names).
    Looks up results from a SQL table, defaulting to 'festival_data'.
    """

    def __init__(self, table_name: str = "festival_data"):
        self.table_name = table_name
        self.db_connector = DatabaseConnector()

    def get(self, input_string: str) -> Optional[dict]:
        """
        Attempts to identify a festival and year from a given input string
        and returns structured festival information.

        Returns:
            dict or None: A dictionary with keys `festival`, `year`, and `date` (ISO format),
                          or None if no match is found.
        """
        year = self._extract_year(input_string)
        if not year:
            logging.debug("[FestivalHelper] No year found in input.")
            return None

        query = f"SELECT festival, date FROM {self.table_name} WHERE year = %s"
        connection = self.db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (year,))
                rows = cursor.fetchall()

                input_lower = input_string.lower()
                matches = [
                    (festival, date)
                    for festival, date in rows
                    if festival and festival.lower() in input_lower
                ]

                if not matches:
                    logging.debug("[FestivalHelper] No matching festival found.")
                    return None

                # Choose the longest matching name (most specific)
                matches.sort(key=lambda x: len(x[0]), reverse=True)
                best_match = matches[0]

                return {
                    "festival": best_match[0],
                    "year": year,
                    "date": best_match[1].isoformat()
                }

        except Exception as e:
            logging.error(f"[FestivalHelper] Error querying {self.table_name}: {e}")
            return None
        finally:
            connection.close()

    def _extract_year(self, text: str) -> Optional[int]:
        """
        Extracts a 4-digit year (starting with 20xx) from the input string.

        Returns:
            int or None: The extracted year, or None if not found.
        """
        match = re.search(r"\b(20\d{2})\b", text)
        return int(match.group(1)) if match else None
