"""What a listen records beyond the fact that it happened.

Two things a Wrapped cannot be built without: how long the track was actually played, and where it
was played. Both are optional on the wire, because a client that has not been updated has to keep
scrobbling successfully -- so the interesting cases here are the absent ones.
"""

import sys
import unittest
from unittest.mock import MagicMock, patch

for _mod_name in ('dbutils', 'dbutils.pooled_db', 'pymysql', 'mutagen', 'mutagen.easyid3', 'markdown'):
    sys.modules.setdefault(_mod_name, MagicMock())

import services.music_manager.routers.users

services.music_manager.routers.users.run_lms_db_sync = lambda: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)
from fastapi.testclient import TestClient

from services.music_manager.api_key import resolve_system_api_key
from services.music_manager.main import app
from services.music_manager.routers.scrobbler import init_db
from services.music_manager.scrobble_matching import MatchTier
from services.music_manager.tests.scripted_cursor import ScriptedCursor


def statement_for(cursor, fragment):
    """The first executed statement containing `fragment`, with its parameters."""
    for sql, params in cursor.executed:
        if fragment in ' '.join(sql.split()):
            return ' '.join(sql.split()), params
    raise AssertionError(f'no statement containing {fragment!r} in {cursor.executed!r}')


class ScrobbleEventTest(unittest.TestCase):
    """POST /api/scrobble/event, from the client's side of the wire."""

    def setUp(self):
        self.client = TestClient(app)
        self.api_key = resolve_system_api_key()
        self.cursor = ScriptedCursor()
        self.conn = MagicMock()
        self.conn.cursor.return_value.__enter__.return_value = self.cursor

    def post(self, **overrides):
        payload = {'artist_name': 'Angerfist', 'track_title': 'Raise Your Fist', 'username': 'user'}
        payload.update(overrides)
        return self.client.post('/api/scrobble/event', json=payload, headers={'x-api-key': self.api_key})

    def run_matched(self, **overrides):
        """Post an event that resolves to track 42, and hand back the INSERT it produced."""
        with (
            patch('services.music_manager.routers.scrobbler.get_db_connection', return_value=self.conn),
            patch('services.music_manager.routers.scrobbler.find_track', return_value=(42, MatchTier.EXACT, None)),
        ):
            response = self.post(**overrides)
        self.assertEqual(response.status_code, 200, response.text)
        return statement_for(self.cursor, 'INSERT INTO scrobble_listens')

    def run_unmatched(self, **overrides):
        """Post an event that resolves to nothing, and hand back the INSERT it produced."""
        with (
            patch('services.music_manager.routers.scrobbler.get_db_connection', return_value=self.conn),
            patch('services.music_manager.routers.scrobbler.find_track', return_value=None),
        ):
            response = self.post(**overrides)
        self.assertEqual(response.status_code, 200, response.text)
        return statement_for(self.cursor, 'INSERT INTO scrobble_unmatched_listens')

    def test_played_seconds_are_stored_on_a_matched_listen(self):
        sql, params = self.run_matched(played_secs=247)
        self.assertIn('played_secs', sql)
        self.assertIn(247, params)

    def test_a_client_that_reports_no_playing_time_still_scrobbles(self):
        sql, params = self.run_matched()
        self.assertIn('played_secs', sql)
        self.assertIn(None, params)

    def test_a_non_positive_playing_time_is_stored_as_absent(self):
        # Zero is a client with nothing to report, not a track that played for no time.
        for value in (0, -5):
            with self.subTest(value=value):
                self.setUp()
                _sql, params = self.run_matched(played_secs=value)
                self.assertNotIn(value, params)
                self.assertIn(None, params)

    def test_played_seconds_survive_onto_an_unmatched_listen(self):
        sql, params = self.run_unmatched(played_secs=90)
        self.assertIn('played_secs', sql)
        self.assertIn(90, params)

    def test_the_origin_is_stored_verbatim(self):
        # 'auto' is the car. The point of the wider vocabulary is that the server does not
        # interpret it -- it stores what the client said.
        _sql, params = self.run_matched(source='auto')
        self.assertIn('auto', params)

    def test_the_origin_defaults_to_manual_when_the_client_says_nothing(self):
        _sql, params = self.run_matched()
        self.assertIn('manual', params)


class InitDbTest(unittest.TestCase):
    """The column has to appear on a database that predates it, not only on a fresh one."""

    @staticmethod
    def _column_alters(cursor):
        """Only the played_secs ALTERs. The index ALTERs beside them are
        unconditional -- `ADD INDEX IF NOT EXISTS` needs no guard -- so counting
        every ALTER would make this test fail whenever an index is added."""
        return [sql for sql, _params in cursor.executed if 'ALTER TABLE' in sql and 'played_secs' in sql]

    def test_the_column_is_added_when_it_is_missing(self):
        cursor = ScriptedCursor()  # every SHOW COLUMNS reads as "no such column"
        init_db(cursor)
        altered = self._column_alters(cursor)
        self.assertEqual(len(altered), 2, altered)

    def test_it_is_a_no_op_when_the_column_is_already_there(self):
        cursor = ScriptedCursor(rules=[("SHOW COLUMNS", None, {'Field': 'played_secs'})])
        init_db(cursor)
        self.assertEqual(self._column_alters(cursor), [])

    def test_the_listened_at_indexes_are_created_on_an_existing_database(self):
        """Reading history back scans on listened_at with no username to seek on;
        the unique keys lead on username and cannot serve that."""
        cursor = ScriptedCursor(rules=[("SHOW COLUMNS", None, {'Field': 'played_secs'})])
        init_db(cursor)
        indexed = [sql for sql, _params in cursor.executed if 'ADD INDEX' in sql and 'listened_at' in sql]
        self.assertEqual(len(indexed), 2, indexed)

    def test_the_track_index_is_created_on_an_existing_database(self):
        """Per-track listen questions seek on track_id, which no key led with."""
        cursor = ScriptedCursor(rules=[("SHOW COLUMNS", None, {'Field': 'played_secs'})])
        init_db(cursor)
        indexed = [sql for sql, _params in cursor.executed if 'ADD INDEX' in sql and 'idx_listens_track_user' in sql]
        self.assertEqual(len(indexed), 1, indexed)
        self.assertIn('(track_id, username)', indexed[0])

    def test_a_fresh_table_declares_its_listened_at_default(self):
        """An undeclared DEFAULT on the first TIMESTAMP column means ON UPDATE on MariaDB
        < 10.10 (docs/bug-reports/039)."""
        cursor = ScriptedCursor()
        init_db(cursor)
        creates = [sql for sql, _params in cursor.executed if 'CREATE TABLE IF NOT EXISTS scrobble_' in sql]
        listens = [sql for sql in creates if 'listened_at' in sql]
        self.assertEqual(len(listens), 2, creates)
        for sql in listens:
            self.assertIn('listened_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,', sql)
            self.assertNotIn('ON UPDATE', sql)

    @staticmethod
    def _listened_at_modifies(cursor):
        return [sql for sql, _params in cursor.executed if 'MODIFY listened_at' in sql]

    def test_an_old_table_loses_its_on_update_at_start_up(self):
        cursor = ScriptedCursor(
            rules=[("SHOW COLUMNS", None, {'Field': 'played_secs'}), ('information_schema', None, {'n': 1})]
        )
        init_db(cursor)
        modified = self._listened_at_modifies(cursor)
        self.assertEqual(len(modified), 2, modified)
        self.assertTrue(all('ON UPDATE' not in sql for sql in modified), modified)

    def test_a_repaired_table_is_not_altered_again(self):
        """The MODIFY copies the whole table (the long UNIQUE key is a hash key), so it
        must only run while the attribute is still there."""
        cursor = ScriptedCursor(
            rules=[("SHOW COLUMNS", None, {'Field': 'played_secs'}), ('information_schema', None, {'n': 0})]
        )
        init_db(cursor)
        self.assertEqual(self._listened_at_modifies(cursor), [])


if __name__ == '__main__':
    unittest.main()
