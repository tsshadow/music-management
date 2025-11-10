import logging
from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


# Static list of tables that should exist in the database.
REQUIRED_TABLES = [
    "soundcloud_accounts",
    "soundcloud_archive",
    "youtube_accounts",
    "youtube_archive",
    "artists",
    "artist_genre",
    "catid_label",
    "festival_data",
    "genres",
    "ignored_artists",
    "ignored_genres",
    "label_genre",
    "subgenre_genre",
]


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

    queries = [table_queries[table] for table in REQUIRED_TABLES]

    try:
        conn = DatabaseConnector().connect()
        try:
            with conn.cursor() as cursor:
                for query in queries:
                    print(query)
                    cursor.execute(query)
            conn.commit()
        finally:
            conn.close()
    except Exception as exc:  # pragma: no cover - defensive
        logging.warning("Failed to ensure DB tables exist: %s", exc)
