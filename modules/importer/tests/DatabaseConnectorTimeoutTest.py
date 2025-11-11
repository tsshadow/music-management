import importlib
import os
import sys
import unittest
from unittest.mock import patch


class DatabaseConnectorTimeoutTest(unittest.TestCase):
    def setUp(self):
        os.environ.setdefault('DB_HOST', 'localhost')
        os.environ.setdefault('DB_USER', 'user')
        os.environ.setdefault('DB_PORT', '0')
        os.environ.setdefault('DB_PASS', '')
        os.environ.setdefault('DB_DB', 'db')
        sys.modules.pop('postprocessing.Song.Helpers.DatabaseConnector', None)
        sys.modules.pop('modules.importer.postprocessing.Song.Helpers.DatabaseConnector', None)

    def _load_db_module(self):
        return importlib.import_module('postprocessing.Song.Helpers.DatabaseConnector')

    def test_connect_uses_default_timeout(self):
        db_module = self._load_db_module()
        DatabaseConnector = db_module.DatabaseConnector
        with patch.object(db_module, 'pymysql', create=True) as mock_pymysql:
            DatabaseConnector().connect()
            _, kwargs = mock_pymysql.connect.call_args
            self.assertEqual(kwargs.get('connect_timeout'), 5)

    def test_env_can_override_timeout(self):
        os.environ['DB_CONNECT_TIMEOUT'] = '1'
        db_module = self._load_db_module()
        DatabaseConnector = db_module.DatabaseConnector
        with patch.object(db_module, 'pymysql', create=True) as mock_pymysql:
            DatabaseConnector().connect()
            _, kwargs = mock_pymysql.connect.call_args
            self.assertEqual(kwargs.get('connect_timeout'), 1)
        del os.environ['DB_CONNECT_TIMEOUT']


if __name__ == '__main__':
    unittest.main()
