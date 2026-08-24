import logging

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
        query = f'\n            CREATE TABLE IF NOT EXISTS {self.table_name} (\n                filepath VARCHAR(767) PRIMARY KEY,\n                mtime FLOAT,\n                last_processed TIMESTAMP DEFAULT CURRENT_TIMESTAMP ON UPDATE CURRENT_TIMESTAMP,\n                needs_rescan BOOLEAN DEFAULT FALSE\n            )\n        '
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
                return mtime > db_mtime
        except Exception as e:
            logging.error(f'Error checking if song needs processing: {e}')
            return True
        finally:
            connection.close()

    def mark_processed(self, song_path: str, mtime: float):
        """Marks a song as processed in the database."""
        query = f'\n            INSERT INTO {self.table_name} (filepath, mtime, needs_rescan)\n            VALUES (%s, %s, FALSE)\n            ON DUPLICATE KEY UPDATE mtime = VALUES(mtime), needs_rescan = FALSE\n        '
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (song_path, mtime))
            connection.commit()
        except Exception as e:
            logging.error(f'Error marking song as processed: {e}')
        finally:
            connection.close()

    def mark_stale_for_rescan(self, older_than_days: int, limit: int) -> int:
        """Hands the oldest rows back to the tagger, at most `limit` of them.

        Rows that are already queued are left alone, so a file that keeps failing cannot
        crowd out the rest of the library. `last_processed` is refreshed by
        mark_processed, which is what makes the whole library cycle past the current
        rules once every `older_than_days`.
        """
        query = f'\n            UPDATE {self.table_name} SET needs_rescan = TRUE\n            WHERE needs_rescan = FALSE AND last_processed < NOW() - INTERVAL %s DAY\n            ORDER BY last_processed\n            LIMIT %s\n        '
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (older_than_days, limit))
                marked = cursor.rowcount
            connection.commit()
            return marked
        except Exception as e:
            logging.error(f'Error queueing stale songs for rescan: {e}')
            return 0
        finally:
            connection.close()

    def count_stale(self, older_than_days: int) -> int:
        """How many rows are still waiting to be handed back to the tagger."""
        query = f'\n            SELECT COUNT(*) FROM {self.table_name}\n            WHERE needs_rescan = FALSE AND last_processed < NOW() - INTERVAL %s DAY\n        '
        connection = self.db_connector.connect()
        try:
            with connection.cursor() as cursor:
                cursor.execute(query, (older_than_days,))
                result = cursor.fetchone()
                return result[0] if result else 0
        except Exception as e:
            logging.error(f'Error counting stale songs: {e}')
            return 0
        finally:
            connection.close()

    def mark_for_rescan(self, song_path: str=None):
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