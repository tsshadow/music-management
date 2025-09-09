import logging
import re
from pathlib import Path
from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


def _is_table_referenced(table: str) -> bool:
    """Return True if *table* appears anywhere in the project code base."""
    root = Path(__file__).resolve().parents[1]
    pattern = re.compile(r"\b" + re.escape(table) + r"\b")
    for path in root.rglob("*.py"):
        if path == Path(__file__):
            continue
        try:
            if pattern.search(path.read_text(encoding="utf-8")):
                return True
        except Exception:  # pragma: no cover - best effort
            continue
    return False


def ensure_tables_exist() -> None:
    """Ensure required database tables exist."""
    table_queries = {
        "soundcloud_accounts": """
            CREATE TABLE IF NOT EXISTS soundcloud_accounts (
                name VARCHAR(255),
                soundcloud_id VARCHAR(255),
                PRIMARY KEY (name)
            )
        """,
        "soundcloud_archive": """
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
        "youtube_accounts": """
            CREATE TABLE IF NOT EXISTS youtube_accounts (
                name VARCHAR(255) PRIMARY KEY
            )
        """,
        "youtube_archive": """
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
        "artists": """
            CREATE TABLE IF NOT EXISTS artists (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                INDEX(name)
            )
        """,
        "artist_genre": """
            CREATE TABLE IF NOT EXISTS artist_genre (
                artist VARCHAR(255) NOT NULL,
                genre VARCHAR(255) NOT NULL,
                PRIMARY KEY (artist, genre)
            )
        """,
        "catid_label": """
            CREATE TABLE IF NOT EXISTS catid_label (
                catid VARCHAR(255) PRIMARY KEY,
                label VARCHAR(255) NOT NULL
            )
        """,
        "festival_data": """
            CREATE TABLE IF NOT EXISTS festival_data (
                festival VARCHAR(255) NOT NULL,
                year INT NOT NULL,
                date DATE NOT NULL,
                PRIMARY KEY (festival, year)
            )
        """,
        "genres": """
            CREATE TABLE IF NOT EXISTS genres (
                genre VARCHAR(255) NOT NULL,
                corrected_genre VARCHAR(255) NOT NULL,
                PRIMARY KEY (genre)
            )
        """,
        "ignored_artists": """
            CREATE TABLE IF NOT EXISTS ignored_artists (
                id INT AUTO_INCREMENT PRIMARY KEY,
                name VARCHAR(255) NOT NULL,
                corrected_name VARCHAR(255),
                INDEX(name)
            )
        """,
        "ignored_genres": """
            CREATE TABLE IF NOT EXISTS ignored_genres (
                name VARCHAR(255) PRIMARY KEY,
                corrected_name VARCHAR(255)
            )
        """,
        "label_genre": """
            CREATE TABLE IF NOT EXISTS label_genre (
                label VARCHAR(255) NOT NULL,
                genre VARCHAR(255) NOT NULL,
                PRIMARY KEY (label, genre)
            )
        """,
        "subgenre_genre": """
            CREATE TABLE IF NOT EXISTS subgenre_genre (
                subgenre VARCHAR(255) NOT NULL,
                genre VARCHAR(255) NOT NULL,
                PRIMARY KEY (subgenre, genre)
            )
        """,
    }

    queries = [sql for table, sql in table_queries.items() if _is_table_referenced(table)]

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
