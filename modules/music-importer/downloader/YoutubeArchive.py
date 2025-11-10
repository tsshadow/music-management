import logging

from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


class YoutubeArchive:
    """Utility helpers for interacting with the `youtube_archive` table."""

    @staticmethod
    def exists(account: str, video_id: str) -> bool:
        """Return True if the given video was already archived for the account."""
        try:
            conn = DatabaseConnector().connect()
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT 1 FROM youtube_archive WHERE account = %s AND video_id = %s
                    """,
                    (account, video_id),
                )
                return cursor.fetchone() is not None
        except Exception as e:
            logging.warning(
                f"Could not check archive for {account}/{video_id}: {e}", exc_info=True
            )
            return False

    @staticmethod
    def insert(account: str, video_id: str, path: str, url: str, title: str):
        """Insert a newly downloaded track into the youtube_archive table."""
        if not all([account, video_id, url]):
            logging.warning(
                f"Missing fields for archive insert: account={account}, video_id={video_id}, url={url}"
            )
            return

        try:
            conn = DatabaseConnector().connect()
            with conn.cursor() as cursor:
                # Ensure account exists in youtube_accounts table
                cursor.execute(
                    "INSERT IGNORE INTO youtube_accounts (name) VALUES (%s)", (account,)
                )

                cursor.execute(
                    """
                    INSERT IGNORE INTO youtube_archive (account, video_id, filename, url, title)
                    VALUES (%s, %s, %s, %s, %s)
                    """,
                    (account, video_id, path, url, title),
                )

                conn.commit()
                logging.debug(f"Added to youtube_archive: {account}/{video_id}")
        except Exception as e:
            logging.error(
                f"Failed to insert archive info for {path}: {e}", exc_info=True
            )

