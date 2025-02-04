import os
import pymysql
import logging

class DatabaseConnector:
    _instance = None  # Singleton instance

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(DatabaseConnector, cls).__new__(cls)
            cls._instance._init_connection()  # Initialize only once
        return cls._instance

    def _init_connection(self):
        self.host = os.getenv('DB_HOST')
        self.user = os.getenv('DB_USER')
        self.port = int(os.getenv('DB_PORT'))
        self.password = os.getenv('DB_PASS')
        self.db = os.getenv('DB_DB')
        self.connection = None

    def connect(self):
        if not self.connection or not self.connection.open:
            self.connection = pymysql.connect(
                host=self.host,
                port=self.port,
                user=self.user,
                password=self.password,
                db=self.db
            )
        return self.connection
