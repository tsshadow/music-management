import threading
import logging
import pymysql
import queue
from typing import Tuple, List

from api.config_store import ConfigStore

class Analyzer(threading.Thread):
    def __init__(self):
        super().__init__()
        self._store = ConfigStore()
        self._db_keys = ["db_host", "db_user", "db_port", "db_pass", "db_connect_timeout"]
        self._apply_config()
        for key in self._db_keys:
            self._store.subscribe(key, lambda _value, k=key: self._apply_config())

        self.conn = pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            database="music-analyzer",
            autocommit=True,
            connect_timeout=self.connect_timeout,
        )
        self.cursor = self.conn.cursor()

        self.queue = queue.Queue()
        self._running = True

    def start(self):
        """Start the analyzer thread and clear previous analysis data."""
        self._truncate_tables()
        super().start()

    def _truncate_tables(self):
        logging.info("Clearing existing analysis data...")
        self.cursor.execute("SET FOREIGN_KEY_CHECKS = 0")
        self.cursor.execute("TRUNCATE TABLE artists_genres")
        self.cursor.execute("TRUNCATE TABLE artists")
        self.cursor.execute("TRUNCATE TABLE genres")
        self.cursor.execute("SET FOREIGN_KEY_CHECKS = 1")

    def run(self):
        logging.info("Analyzer DB thread started")
        while self._running or not self.queue.empty():
            try:
                item = self.queue.get(timeout=1)
                if item == "STOP":
                    break
                artist, genre = item
                self._process(artist, genre)
            except queue.Empty:
                continue
        logging.info("Analyzer DB thread finished")

    def stop(self):
        self._running = False
        self.queue.put("STOP")

    def _process(self, artist: str, genre: str):
        artist_id = self._insert_or_update_artist(artist)
        if genre:
            genre_id = self._insert_or_get_genre(genre)
            self._insert_or_update_artist_genre(artist_id, genre_id)

    def submit(self, artist: str, genre: str):
        self.queue.put((artist, genre))

    def _insert_or_update_artist(self, name: str) -> int:
        self.cursor.execute("""
            INSERT INTO artists (name, count)
            VALUES (%s, 1)
            ON DUPLICATE KEY UPDATE count = count + 1
        """, (name,))
        self.cursor.execute("SELECT id FROM artists WHERE name = %s", (name,))
        return self.cursor.fetchone()[0]

    def _insert_or_get_genre(self, name: str) -> int:
        self.cursor.execute("""
            INSERT INTO genres (name)
            VALUES (%s)
            ON DUPLICATE KEY UPDATE name = name
        """, (name,))
        self.cursor.execute("SELECT id FROM genres WHERE name = %s", (name,))
        return self.cursor.fetchone()[0]

    def _insert_or_update_artist_genre(self, artist_id: int, genre_id: int):
        self.cursor.execute("""
            INSERT INTO artists_genres (artist_id, genre_id, count)
            VALUES (%s, %s, 1)
            ON DUPLICATE KEY UPDATE count = count + 1
        """, (artist_id, genre_id))

    def get_suspect_artists(self, threshold=1) -> List[str]:
        self.cursor.execute("""
            SELECT name FROM artists WHERE count <= %s
        """, (threshold,))
        return [row[0] for row in self.cursor.fetchall()]

    def done(self):
        self.stop()
        self.join()
        self.cursor.close()
        self.conn.close()

    def _apply_config(self) -> None:
        values = self._store.get_many(self._db_keys)
        self.host = values.get("db_host") or None
        self.user = values.get("db_user") or None
        port = values.get("db_port")
        self.port = int(port) if port else None
        self.password = values.get("db_pass") or None
        timeout = values.get("db_connect_timeout")
        self.connect_timeout = int(timeout) if timeout else 5
