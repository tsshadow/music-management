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

    def test_the_column_is_added_when_it_is_missing(self):
        cursor = ScriptedCursor()  # every SHOW COLUMNS reads as "no such column"
        init_db(cursor)
        altered = [sql for sql, _params in cursor.executed if 'ALTER TABLE' in sql]
        self.assertEqual(len(altered), 2, altered)
        self.assertTrue(all('played_secs' in sql for sql in altered), altered)

    def test_it_is_a_no_op_when_the_column_is_already_there(self):
        cursor = ScriptedCursor(rules=[("SHOW COLUMNS", None, {'Field': 'played_secs'})])
        init_db(cursor)
        altered = [sql for sql, _params in cursor.executed if 'ALTER TABLE' in sql]
        self.assertEqual(altered, [])


if __name__ == '__main__':
    unittest.main()
