import logging
import os
from typing import List

import pymysql

from api.config_store import ConfigStore


class DatabaseConnector:
    def __init__(self):
        self._store = ConfigStore()
        self._keys = ["db_host", "db_user", "db_port", "db_pass", "db_name", "db_connect_timeout"]
        self._subscriptions = []
        self._apply_config()
        for key in self._keys:
            self._subscriptions.append(
                self._store.subscribe(key, lambda _value, k=key: self._apply_config())
            )

    def connect(self):
        missing = [
            name
            for name, value in {
                "host": self.host,
                "user": self.user,
                "database": self.db,
            }.items()
            if value in (None, "")
        ]
        if self.port is None:
            missing.append("port")
        if missing:
            raise RuntimeError(
                "Database credentials are not fully configured: " + ", ".join(missing)
            )
        return pymysql.connect(
            host=self.host,
            port=int(self.port),
            user=self.user,
            password=self.password,
            db=self.db,
            connect_timeout=self.connect_timeout,
        )

    def get_youtube_accounts(self) -> List[str]:
        """Return the configured YouTube channel list.

        Falls back to an empty list when the database cannot be reached so
        callers like the downloader can safely no-op instead of crashing.
        """

        try:
            conn = self.connect()
        except Exception as exc:  # pragma: no cover - defensive guardrail
            logging.error("Unable to connect to database for YouTube accounts: %s", exc)
            return []

        try:
            with conn.cursor() as cursor:
                cursor.execute("SELECT name FROM youtube_accounts ORDER BY name")
                rows = cursor.fetchall()
        except Exception as exc:  # pragma: no cover - defensive guardrail
            logging.error("Failed to fetch YouTube accounts: %s", exc)
            return []
        finally:
            try:
                conn.close()
            except Exception:  # pragma: no cover - best effort cleanup
                pass

        return [row[0] for row in rows if row and row[0]]

    def _apply_config(self) -> None:
        values = self._store.get_many(self._keys)
        self.host = values.get("db_host") or None
        self.user = values.get("db_user") or None
        self.port = values.get("db_port")
        if self.port is not None and not isinstance(self.port, int):
            try:
                self.port = int(self.port)
            except (TypeError, ValueError):
                logging.warning("Invalid db_port value %r", self.port)
                self.port = None
        self.password = values.get("db_pass") or None
        self.db = values.get("db_name") or None
        timeout = values.get("db_connect_timeout")
        try:
            self.connect_timeout = int(timeout) if timeout is not None else 5
        except (TypeError, ValueError):
            logging.warning("Invalid db_connect_timeout value %r", timeout)
            self.connect_timeout = 5

        override_timeout = os.getenv("DB_CONNECT_TIMEOUT")
        if override_timeout is not None:
            try:
                self.connect_timeout = int(override_timeout)
            except (TypeError, ValueError):
                logging.warning("Invalid DB_CONNECT_TIMEOUT override %r", override_timeout)
