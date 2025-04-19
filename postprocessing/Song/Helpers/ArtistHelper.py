import logging
from data.DatabaseConnector import DatabaseConnector


class ArtistHelper:
    """
    Utility class for artist-related string transformations,
    including smart recapitalization using a database of known artists.
    """

    @staticmethod
    def recapitalize(name: str) -> str:
        """
        Attempts to retrieve the canonical capitalization of an artist name
        from the database. Falls back to title-cased version if not found.

        Args:
            name (str): The artist name to normalize.

        Returns:
            str: Canonically capitalized artist name if found, otherwise title-cased input.
        """
        query = "SELECT name FROM artists WHERE LOWER(name) = %s"
        db_connector = DatabaseConnector()
        connection = db_connector.connect()

        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (name.lower(),))
                result = cursor.fetchone()
                return result[0] if result else name.title()
        except Exception as e:
            logging.error(f"Error querying artist name: {e}")
            return name.title()
