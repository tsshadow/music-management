import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

# mock_base swaps services.common.Helpers.DatabaseConnector for a stub so that no test
# can open a real socket. That stub has no pymysql to patch, so load the real source
# file under a throwaway module name and exercise that instead.
_REAL_SOURCE = Path(__file__).resolve().parents[1] / 'common' / 'Helpers' / 'DatabaseConnector.py'


def _load_real_module():
    spec = importlib.util.spec_from_file_location('_real_database_connector', _REAL_SOURCE)
    module = importlib.util.module_from_spec(spec)
    sys.modules['pymysql'] = MagicMock()
    spec.loader.exec_module(module)
    return module


class DatabaseConnectorTimeoutTest(unittest.TestCase):
    def setUp(self):
        os.environ['DB_HOST'] = 'localhost'
        os.environ['DB_USER'] = 'user'
        os.environ['DB_PORT'] = '3306'
        os.environ['DB_PASS'] = 'secret'
        os.environ['DB_DB'] = 'db'
        os.environ.pop('DB_CONNECT_TIMEOUT', None)
        self.db_module = _load_real_module()

    def test_connect_uses_default_timeout(self):
        with patch.object(self.db_module, 'pymysql') as mock_pymysql:
            self.db_module.DatabaseConnector().connect()
            _, kwargs = mock_pymysql.connect.call_args
            self.assertEqual(kwargs.get('connect_timeout'), 5)

    def test_env_can_override_timeout(self):
        os.environ['DB_CONNECT_TIMEOUT'] = '1'
        try:
            with patch.object(self.db_module, 'pymysql') as mock_pymysql:
                self.db_module.DatabaseConnector().connect()
                _, kwargs = mock_pymysql.connect.call_args
                self.assertEqual(kwargs.get('connect_timeout'), 1)
        finally:
            del os.environ['DB_CONNECT_TIMEOUT']

    def test_connect_passes_the_configured_credentials(self):
        with patch.object(self.db_module, 'pymysql') as mock_pymysql:
            self.db_module.DatabaseConnector().connect()
            _, kwargs = mock_pymysql.connect.call_args
            self.assertEqual(kwargs.get('host'), 'localhost')
            self.assertEqual(kwargs.get('port'), 3306)
            self.assertEqual(kwargs.get('user'), 'user')
            self.assertEqual(kwargs.get('password'), 'secret')
            self.assertEqual(kwargs.get('db'), 'db')

    def test_a_host_with_an_inline_port_is_split(self):
        os.environ['DB_HOST'] = 'db.internal:3307'
        connector = self.db_module.DatabaseConnector()
        self.assertEqual(connector.host, 'db.internal')
        self.assertEqual(connector.port, 3307)

    def test_an_ipv6_host_keeps_its_brackets_and_the_separate_port(self):
        os.environ['DB_HOST'] = '[::1]'
        connector = self.db_module.DatabaseConnector()
        self.assertEqual(connector.host, '[::1]')
        self.assertEqual(connector.port, 3306)

    def test_an_unparseable_port_falls_back_to_none(self):
        os.environ['DB_PORT'] = 'not-a-number'
        connector = self.db_module.DatabaseConnector()
        self.assertIsNone(connector.port)

    def test_connect_refuses_to_run_with_incomplete_configuration(self):
        os.environ['DB_HOST'] = ''
        connector = self.db_module.DatabaseConnector()
        with self.assertRaises(RuntimeError):
            connector.connect()


if __name__ == '__main__':
    unittest.main()
