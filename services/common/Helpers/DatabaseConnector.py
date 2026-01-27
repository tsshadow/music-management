import os
import pymysql
import logging

class DatabaseConnector:

    def __init__(self):
        self.host = os.getenv('DB_HOST')
        self.user = os.getenv('DB_USER')
        port = os.getenv('DB_PORT')
        try:
            self.port = int(port) if port else None
        except (TypeError, ValueError):
            logging.warning('Invalid DB_PORT value %r', port)
            self.port = None
        self.password = os.getenv('DB_PASS')
        self.db = os.getenv('DB_DB')
        self.connect_timeout = int(os.getenv('DB_CONNECT_TIMEOUT', '5'))

    def connect(self):
        if not all([self.host, self.user, self.db, self.port]):
            raise RuntimeError('Database connection parameters are not fully configured (host, user, db, port are required)')
        return pymysql.connect(host=self.host, port=self.port, user=self.user, password=self.password, db=self.db, connect_timeout=self.connect_timeout)

    def verify_connection(self):
        """
        Verify that the database connection is working.

        Raises:
            RuntimeError: If database connection cannot be established
        """
        try:
            connection = self.connect()
            with connection.cursor() as cursor:
                cursor.execute('SELECT 1')
                cursor.fetchone()
            connection.close()
            logging.info('Database connection verified successfully')
        except pymysql.Error as e:
            logging.error('Database connection failed: %s', e)
            raise RuntimeError(f'Cannot connect to database: {e}') from e
        except Exception as e:
            logging.error('Unexpected error during database connection verification: %s', e)
            raise RuntimeError(f'Database connection verification failed: {e}') from e