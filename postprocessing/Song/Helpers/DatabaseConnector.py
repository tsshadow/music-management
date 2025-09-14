import os
import pymysql
import logging

class DatabaseConnector:
    def __init__(self):
        self.host = os.getenv("DB_HOST")
        self.user = os.getenv("DB_USER")
        port = os.getenv("DB_PORT")
        try:
            self.port = int(port) if port else None
        except (TypeError, ValueError):
            logging.warning("Invalid DB_PORT value %r", port)
            self.port = None
        self.password = os.getenv("DB_PASS")
        self.db = os.getenv("DB_DB")
        # Fail fast if the database cannot be reached
        self.connect_timeout = int(os.getenv('DB_CONNECT_TIMEOUT', '5'))

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
