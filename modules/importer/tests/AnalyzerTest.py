import os
import sys
import types
import unittest

# Provide required environment variables
os.environ.setdefault('DB_HOST', 'localhost')
os.environ.setdefault('DB_USER', 'user')
os.environ.setdefault('DB_PORT', '3306')
os.environ.setdefault('DB_PASS', 'pass')

# Stub pymysql.connect
class DummyCursor:
    def execute(self, *a, **k):
        pass
    def fetchone(self):
        return [1]
    def close(self):
        pass

class DummyConnection:
    def cursor(self):
        return DummyCursor()
    def close(self):
        pass

def dummy_connect(*a, **k):
    return DummyConnection()

pymysql_mod = types.ModuleType('pymysql')
pymysql_mod.connect = dummy_connect
sys.modules['pymysql'] = pymysql_mod

from postprocessing.analyzer import Analyzer

class AnalyzerTest(unittest.TestCase):
    def test_truncate_called_on_start_only(self):
        calls = []
        original = Analyzer._truncate_tables
        Analyzer._truncate_tables = lambda self: calls.append(True)
        try:
            analyzer = Analyzer()
            # _truncate_tables should not have been called during initialization
            self.assertEqual(calls, [])
            analyzer.start()
            analyzer.stop()
            analyzer.join()
            # now _truncate_tables should have been called exactly once
            self.assertEqual(calls, [True])
        finally:
            Analyzer._truncate_tables = original

if __name__ == '__main__':
    unittest.main()
