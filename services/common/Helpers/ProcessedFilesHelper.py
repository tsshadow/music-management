import logging
from contextlib import closing
from services.common.Helpers.DatabaseConnector import DatabaseConnector

class ProcessedFilesHelper:
    """
    Helper class to track processed song files in the database.
    Stores song path and modification time to avoid redundant tagging.
    """

    def __init__(self, table_name='tagger_processed_files'):
        self.table_name = table_name
        self.db_connector = DatabaseConnector()

    def create_table(self):
        """Creates the table if it doesn't exist."""
        query = f"""
            CREATE TABLE IF NOT EXISTS {self.table_name} (
                filepath VARCHAR(767) PRIMARY KEY,
                mtime FLOAT,
                last_processed TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,
                needs_rescan BOOLEAN DEFAULT FALSE
            )
        """
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query)
            connection.commit()
        except Exception as e:
            logging.error(f'Error creating {self.table_name}: {e}')
        finally:
            connection.close()

    def needs_processing(self, song_path: str, mtime: float) -> bool:
        """
        Checks if a song needs to be processed.
        Returns True if the song is not in the database, its mtime has changed,
        or it has been explicitly marked for rescan.
        """
        query = f'SELECT mtime, needs_rescan FROM {self.table_name} WHERE filepath = %s'
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (song_path,))
                result = cursor.fetchone()
                if not result:
                    return True
                
                db_mtime, needs_rescan = result
                if needs_rescan:
                    return True
                
                # Use a small epsilon for float comparison if necessary, but mtime is usually exact
                return mtime > db_mtime
        except Exception as e:
            logging.error(f'Error checking if song needs processing: {e}')
            return True # Default to True on error to be safe
        finally:
            connection.close()

    def mark_processed(self, song_path: str, mtime: float):
        """Marks a song as processed in the database."""
        query = f"""
            INSERT INTO {self.table_name} (filepath, mtime, needs_rescan)
            VALUES (%s, %s, FALSE)
            ON DUPLICATE KEY UPDATE mtime = VALUES(mtime), needs_rescan = FALSE
        """
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (song_path, mtime))
            connection.commit()
        except Exception as e:
            logging.error(f'Error marking song as processed: {e}')
        finally:
            connection.close()

    def mark_for_rescan(self, song_path: str = None):
        """Marks one or all songs for rescan."""
        if song_path:
            query = f'UPDATE {self.table_name} SET needs_rescan = TRUE WHERE filepath = %s'
            args = (song_path,)
        else:
            query = f'UPDATE {self.table_name} SET needs_rescan = TRUE'
            args = None
            
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, args)
            connection.commit()
        except Exception as e:
            logging.error(f'Error marking songs for rescan: {e}')
        finally:
            connection.close()
