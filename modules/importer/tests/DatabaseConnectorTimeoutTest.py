import os
import unittest
from unittest.mock import patch

from postprocessing.Song.Helpers.DatabaseConnector import DatabaseConnector


class DatabaseConnectorTimeoutTest(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('DB_HOST', 'localhost')
        os.environ.setdefault('DB_USER', 'user')
        os.environ.setdefault('DB_PORT', '0')
        os.environ.setdefault('DB_PASS', '')
        os.environ.setdefault('DB_DB', 'db')

    def test_connect_uses_default_timeout(self):
        import postprocessing.Song.Helpers.DatabaseConnector as db_module
        with patch.object(db_module, 'pymysql') as mock_pymysql:
            DatabaseConnector().connect()
            _, kwargs = mock_pymysql.connect.call_args
            self.assertEqual(kwargs.get('connect_timeout'), 5)

    def test_env_can_override_timeout(self):
        os.environ['DB_CONNECT_TIMEOUT'] = '1'
        import postprocessing.Song.Helpers.DatabaseConnector as db_module
        with patch.object(db_module, 'pymysql') as mock_pymysql:
            DatabaseConnector().connect()
            _, kwargs = mock_pymysql.connect.call_args
            self.assertEqual(kwargs.get('connect_timeout'), 1)
        del os.environ['DB_CONNECT_TIMEOUT']


if __name__ == '__main__':
    unittest.main()
