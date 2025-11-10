import logging
from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector

class BrokenSongHelper:
    """
    Helper class to log broken/corrupt song files in the database.
    Stores song path and error code in the 'broken_songs' table.
    """

    def __init__(self, table_name="broken_songs"):
        self.table_name = table_name
        self.db_connector = DatabaseConnector()

    def add(self, song_path: str, error_code: str):
        """
        Adds a broken song entry to the database.

        Args:
            song_path (str): The absolute path to the problematic song file.
            error_code (str): A short error identifier, e.g. 'MP4StreamInfoError'.
        """
        query = f"""
            INSERT INTO {self.table_name} (path, error_code)
            VALUES (%s, %s)
        """
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (song_path, error_code))
            connection.commit()
        except Exception as e:
            logging.error(f"Error adding broken song to database: {e}")
        finally:
            connection.close()

    def remove(self, song_id: int):
        """
        Removes a broken song entry from the database by its ID.

        Args:
            song_id (int): The ID of the broken song entry to remove.
        """
        query = f"DELETE FROM {self.table_name} WHERE id = %s"
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (song_id,))
            connection.commit()
            logging.info(f"Verwijderd uit database: broken song ID {song_id}")
        except Exception as e:
            logging.error(f"Error removing broken song from database: {e}")
        finally:
            connection.close()

    def get_all(self):
        """
        Fetches all broken song entries from the database.

        Returns:
            List[Tuple[int, str, str]]: A list of tuples containing (id, path, error_code).
        """
        query = f"SELECT id, path, error_code FROM {self.table_name}"
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
                return cursor.fetchall()
        except Exception as e:
            logging.error(f"Error fetching broken songs: {e}")
            return []
        finally:
            connection.close()

