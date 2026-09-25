import logging
import os
from contextlib import contextmanager

import pymysql

from services.common.Helpers import RoundScope


class DatabaseConnector:
    """Connection parameters from the environment, and the one place connections are opened."""

    def __init__(self):
        self.host = os.getenv('DB_HOST')
        port = os.getenv('DB_PORT')

        # Handle host:port format
        if self.host and ':' in self.host and not self.host.startswith('['):
            self.host, port_str = self.host.split(':', 1)
            port = port_str

        self.user = os.getenv('DB_USER')
        try:
            self.port = int(port) if port else None
        except (TypeError, ValueError):
            logging.warning('Invalid DB_PORT value %r', port)
            self.port = None
        self.password = os.getenv('DB_PASS')
        self.db = os.getenv('DB_DB')
        self.connect_timeout = int(os.getenv('DB_CONNECT_TIMEOUT', '5'))

    def connect(self):
        """A connection to the configured database.

        Inside a tagging round (see RoundScope) this is the calling thread's round
        connection, whose `close()` ends the transaction rather than the socket; outside
        one it is a fresh connection, as it always was.
        """
        if not all([self.host, self.user, self.password, self.db, self.port]):
            raise RuntimeError('Database connection parameters are not fully configured')
        return RoundScope.connect(self._open)

    def _open(self):
        """A new pymysql connection; nothing pools or reuses it."""
        return pymysql.connect(
            host=self.host,
            port=self.port,
            user=self.user,
            password=self.password,
            db=self.db,
            connect_timeout=self.connect_timeout,
        )

    @contextmanager
    def connection(self):
        """Yield a connection and always close it again.

        `connect()` opens a fresh socket every call -- nothing pools or reclaims
        them. A caller that just drops the reference leaves the server to notice
        the half-open socket itself, which MariaDB records as "Aborted connection
        ... (Got an error reading communication packets)". Prefer this over a
        bare `connect()` so the close cannot be forgotten.
        """
        connection = self.connect()
        try:
            yield connection
        finally:
            try:
                connection.close()
            except Exception:  # noqa: BLE001 - a close that fails must not mask the real error
                logging.debug('Ignoring failure while closing database connection', exc_info=True)
