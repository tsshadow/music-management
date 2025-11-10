import logging

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
        if not all([self.host, self.user, self.password, self.db, self.port]):
            raise RuntimeError("Database connection parameters are not fully configured")
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.db,
            connect_timeout=self.connect_timeout,
        )

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
