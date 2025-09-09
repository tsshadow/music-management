import logging
from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


def ensure_tables_exist() -> None:
    """Ensure required database tables exist."""
    queries = [
        """
        CREATE TABLE IF NOT EXISTS soundcloud_accounts (
            name VARCHAR(255),
            soundcloud_id VARCHAR(255),
            PRIMARY KEY (name)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS soundcloud_archive (
            id INT AUTO_INCREMENT PRIMARY KEY,
            account VARCHAR(255),
            video_id VARCHAR(255),
            filename TEXT,
            url TEXT,
            title TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX(account),
            INDEX(video_id)
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS youtube_accounts (
            name VARCHAR(255) PRIMARY KEY
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS youtube_archive (
            id INT AUTO_INCREMENT PRIMARY KEY,
            account VARCHAR(255),
            video_id VARCHAR(255),
            filename TEXT,
            url TEXT,
            title TEXT,
            added_at DATETIME DEFAULT CURRENT_TIMESTAMP,
            INDEX(account),
            INDEX(video_id)
        )
        """,
    ]

    try:
        conn = DatabaseConnector().connect()
        try:
            with conn.cursor() as cursor:
                for query in queries:
                    cursor.execute(query)
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Failed to ensure DB tables exist: %s", exc)
