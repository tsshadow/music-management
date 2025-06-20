import os
import pymysql
import logging

class DatabaseConnector:
    def __init__(self):
        self.host = os.getenv('DB_HOST')
        self.user = os.getenv('DB_USER')
        self.port = int(os.getenv('DB_PORT'))
        self.password = os.getenv('DB_PASS')
        self.db = os.getenv('DB_DB')

    def connect(self):
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.db
        )
