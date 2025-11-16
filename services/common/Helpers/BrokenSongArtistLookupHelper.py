import logging

class BrokenSongArtistLookupHelper:
    """
     Helper class to map raw artist names to normalized SoundCloud slugs.
     """

    def __init__(self, table_name='broken_song_artist_lookup'):
        self.table_name = table_name
        self.db_connector = DatabaseConnector()

    def get_normalized_name(self, raw_name: str) -> str:
        """
        Returns the normalized name for a given raw artist name.
        If not found, returns a slugified fallback.
        """
        query = f'\n             SELECT normalized_name FROM {self.table_name}\n             WHERE LOWER(raw_name) = LOWER(%s)\n             LIMIT 1\n         '
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (raw_name,))
                row = cursor.fetchone()
                if row:
                    return row[0]
        except Exception as e:
            logging.error(f"Error looking up normalized artist name for '{raw_name}': {e}")
        finally:
            connection.close()
        return raw_name.strip().lower().replace(' ', '-')

    def insert_if_missing(self, raw_name: str, normalized_name: str):
        """
        Inserts a raw artist name into the table if it doesn't already exist.
        The normalized_name will be left empty.
        """
        check_query = f'\n             SELECT 1 FROM {self.table_name}\n             WHERE LOWER(raw_name) = LOWER(%s)\n             LIMIT 1\n         '
        insert_query = f"\n             INSERT INTO {self.table_name} (raw_name, normalized_name)\n             VALUES (%s, '')\n         "
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(check_query, (raw_name, normalized_name))
                if not cursor.fetchone():
                    cursor.execute(insert_query, (raw_name, normalized_name))
                    connection.commit()
                    logging.info(f"Inserted new raw artist into lookup: '{raw_name} {normalized_name}'")
        except Exception as e:
            logging.error(f"Error inserting raw artist name '{raw_name} {normalized_name}': {e}")
        finally:
            connection.close()