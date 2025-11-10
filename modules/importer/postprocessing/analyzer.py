import logging
import queue
import threading
from typing import List, Tuple

import pymysql

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
        self.stop_event = threading.Event()

    def get_queued(self) -> Tuple[int, List[str]]:
        sql = "SELECT id, artist FROM queue"
        self.cursor.execute(sql)
        rows = self.cursor.fetchall()
        artists = [row[1] for row in rows]
        return len(rows), artists

    def mark_done(self, track_id: int):
        sql = "DELETE FROM queue WHERE id = %s"
        self.cursor.execute(sql, (track_id,))

    def add_to_queue(self, track_id: int, artist: str):
        sql = "INSERT INTO queue (id, artist) VALUES (%s, %s)"
        self.cursor.execute(sql, (track_id, artist))

    def run(self):
        while not self.stop_event.is_set():
            try:
                item = self.queue.get(timeout=1)
            except queue.Empty:
                continue

            track_id, artist = item
            logging.info("Processing artist %s", artist)
            self._process_artist(track_id, artist)
            self.queue.task_done()

    def stop(self):
        self.stop_event.set()
        self.join()
        self.cursor.close()
        self.conn.close()

    def _process_artist(self, track_id: int, artist: str) -> None:
        raise NotImplementedError

    def _apply_config(self) -> None:
        values = self._store.get_many(self._db_keys)
        self.host = values.get("db_host") or None
        self.user = values.get("db_user") or None
        port = values.get("db_port")
        self.port = int(port) if port else None
        self.password = values.get("db_pass") or None
        timeout = values.get("db_connect_timeout")
        self.connect_timeout = int(timeout) if timeout else 5
