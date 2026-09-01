"""Every code path that opens a database connection has to close it again.

`DatabaseConnector.connect()` hands out a brand new pymysql connection on every
call -- there is no pool behind it. A caller that drops the connection without
closing it leaves MariaDB to notice the dead socket on its own, which it logs as
"Aborted connection ... (Got an error reading communication packets)". In
production this filled the server log at ~41k lines/hour, essentially all of it
from a single leaking lookup in the importer.

These tests pin the close, not the query: they assert on `connection.close()`
for the call sites that run in a loop and therefore leak fastest.
"""

import unittest
from contextlib import contextmanager
from unittest.mock import MagicMock, patch

from services.tests.mock_base import setup_mocks

setup_mocks()


class RecordingConnector:
    """Stands in for DatabaseConnector, keeping every connection it handed out.

    Mirrors both entry points of the real class, so a call site is only counted
    as fixed when it actually closes -- switching to `connection()` is not by
    itself what these tests assert on.
    """

    def __init__(self, cursor_rows=None):
        self.connections = []
        self._cursor_rows = cursor_rows

    @contextmanager
    def connection(self):
        connection = self.connect()
        try:
            yield connection
        finally:
            connection.close()

    def connect(self):
        connection = MagicMock()
        cursor = connection.cursor.return_value.__enter__.return_value
        cursor.fetchone.return_value = self._cursor_rows
        cursor.fetchall.return_value = [] if self._cursor_rows is None else [self._cursor_rows]
        self.connections.append(connection)
        return connection

    def assert_all_closed(self, testcase):
        testcase.assertTrue(self.connections, 'no connection was opened at all')
        for index, connection in enumerate(self.connections):
            testcase.assertTrue(connection.close.called, f'connection #{index} was opened but never closed')


class MoverConnectionLeakTest(unittest.TestCase):
    """services/importer/mover.py -- the call site behind the production flood."""

    def _mover(self, connector):
        from services.importer.mover import Mover

        with patch('services.importer.mover.Settings'):
            mover = Mover()
        mover.db_connector = connector
        return mover

    def test_get_label_closes_connection_on_hit(self):
        connector = RecordingConnector(cursor_rows=('Some Label',))
        mover = self._mover(connector)
        self.assertEqual(mover.get_label('CAT001'), 'Some Label')
        connector.assert_all_closed(self)

    def test_get_label_closes_connection_on_miss(self):
        connector = RecordingConnector(cursor_rows=None)
        mover = self._mover(connector)
        self.assertIsNone(mover.get_label('NOPE'))
        connector.assert_all_closed(self)

    def test_get_label_closes_connection_when_query_raises(self):
        connector = RecordingConnector()
        mover = self._mover(connector)

        def explode(*_args, **_kwargs):
            raise RuntimeError('server went away')

        original_connect = connector.connect

        def connect_and_break():
            connection = original_connect()
            connection.cursor.return_value.__enter__.return_value.execute.side_effect = explode
            return connection

        connector.connect = connect_and_break
        self.assertIsNone(mover.get_label('BOOM'))
        connector.assert_all_closed(self)

    def test_repeated_lookups_do_not_accumulate_open_connections(self):
        connector = RecordingConnector(cursor_rows=('Label',))
        mover = self._mover(connector)
        for _ in range(25):
            mover.get_label('CAT001')
        self.assertEqual(len(connector.connections), 25)
        connector.assert_all_closed(self)


class ArchiveConnectionLeakTest(unittest.TestCase):
    """The downloader archives are hit once per candidate track, in a loop."""

    def test_soundcloud_archive_exists_closes_connection(self):
        connector = RecordingConnector(cursor_rows=(1,))
        with patch('services.downloader.soundcloud.SoundcloudArchive.DatabaseConnector', return_value=connector):
            from services.downloader.soundcloud.SoundcloudArchive import SoundcloudArchive

            self.assertTrue(SoundcloudArchive.exists('acct', 'vid'))
        connector.assert_all_closed(self)

    def test_soundcloud_archive_track_exists_closes_connection(self):
        connector = RecordingConnector(cursor_rows=(1,))
        with patch('services.downloader.soundcloud.SoundcloudArchive.DatabaseConnector', return_value=connector):
            from services.downloader.soundcloud.SoundcloudArchive import SoundcloudArchive

            self.assertTrue(SoundcloudArchive.track_exists('123'))
        connector.assert_all_closed(self)

    def test_youtube_archive_exists_closes_connection(self):
        connector = RecordingConnector(cursor_rows=(1,))
        with patch('services.downloader.youtube.YoutubeArchive.DatabaseConnector', return_value=connector):
            from services.downloader.youtube.YoutubeArchive import YoutubeArchive

            self.assertTrue(YoutubeArchive.exists('acct', 'vid'))
        connector.assert_all_closed(self)


class DatabaseConnectorContextManagerTest(unittest.TestCase):
    """The helper that makes the correct pattern the short one."""

    def test_connection_context_manager_closes_on_success(self):
        import importlib.util
        import sys
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / 'common' / 'Helpers' / 'DatabaseConnector.py'
        spec = importlib.util.spec_from_file_location('_leaktest_connector', source)
        module = importlib.util.module_from_spec(spec)
        sys.modules['pymysql'] = MagicMock()
        spec.loader.exec_module(module)

        connector = module.DatabaseConnector()
        opened = MagicMock()
        with patch.object(connector, 'connect', return_value=opened):
            with connector.connection() as connection:
                self.assertIs(connection, opened)
        self.assertTrue(opened.close.called)

    def test_connection_context_manager_closes_on_exception(self):
        import importlib.util
        import sys
        from pathlib import Path

        source = Path(__file__).resolve().parents[1] / 'common' / 'Helpers' / 'DatabaseConnector.py'
        spec = importlib.util.spec_from_file_location('_leaktest_connector2', source)
        module = importlib.util.module_from_spec(spec)
        sys.modules['pymysql'] = MagicMock()
        spec.loader.exec_module(module)

        connector = module.DatabaseConnector()
        opened = MagicMock()
        with patch.object(connector, 'connect', return_value=opened):
            with self.assertRaises(ValueError):
                with connector.connection():
                    raise ValueError('boom')
        self.assertTrue(opened.close.called)


if __name__ == '__main__':
    unittest.main()
