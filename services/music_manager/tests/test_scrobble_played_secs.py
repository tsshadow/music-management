"""What a listen records beyond the fact that it happened.

Two things a Wrapped cannot be built without: how long the track was actually played, and where it
was played. Both are optional on the wire, because a client that has not been updated has to keep
scrobbling successfully -- so the interesting cases here are the absent ones.
"""

import unittest
from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users

services.music_manager.routers.users.run_lms_db_sync = lambda only_sources=None: None
import services.music_manager.database

services.music_manager.database.get_db_connection = MagicMock(return_value=None)
from fastapi.testclient import TestClient

from services.common import schema_tables
from services.music_manager.api_key import resolve_system_api_key
from services.music_manager.main import app
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

    def test_the_clients_start_time_is_the_listen_time(self):
        # Bug report 071: the app sends the moment the play started, LMS relays it as listened_at,
        # and that is the moment the listen is stored under -- not the moment the request arrived.
        _sql, params = self.run_matched(listened_at=1758778000)
        self.assertIn(datetime.fromtimestamp(1758778000), params)

    def test_a_repeated_play_lands_on_the_same_listen(self):
        # The app retries a send it could not confirm. Both requests carry the same start time, so
        # both INSERTs name the same (username, listened_at, track_id) key, and the upsert turns the
        # second into an update of the first rather than a second listen.
        sql, first = self.run_matched(listened_at=1758778000, played_secs=600)
        self.setUp()
        _sql, second = self.run_matched(listened_at=1758778000, played_secs=600)
        self.assertIn('ON DUPLICATE KEY UPDATE', sql)
        self.assertNotIn('listened_at =', sql.split('ON DUPLICATE KEY UPDATE')[1])
        self.assertEqual(first, second)

    def test_a_repeated_unmatched_play_lands_on_the_same_row(self):
        sql, first = self.run_unmatched(listened_at=1758778000)
        self.setUp()
        _sql, second = self.run_unmatched(listened_at=1758778000)
        self.assertIn('ON DUPLICATE KEY UPDATE', sql)
        self.assertEqual(first, second)


class ScrobbleDeclarationTest(unittest.TestCase):
    """What the scrobble tables declare in services/common/schema_tables.py."""

    def statement(self, table):
        return dict(schema_tables.TABLES)[table]

    def test_both_listen_tables_declare_played_secs(self):
        for table in ('scrobble_listens', 'scrobble_unmatched_listens'):
            self.assertIn('`played_secs` int(10) unsigned DEFAULT NULL', self.statement(table))

    def test_listened_at_has_a_default_and_no_on_update(self):
        """An undeclared DEFAULT on the first TIMESTAMP column means ON UPDATE on MariaDB
        < 10.10, and every UPDATE would move the listen to now (docs/bug-reports/039)."""
        for table in ('scrobble_listens', 'scrobble_unmatched_listens'):
            line = next(line for line in self.statement(table).splitlines() if '`listened_at`' in line)
            self.assertIn('NOT NULL DEFAULT current_timestamp()', line)
            self.assertNotIn('ON UPDATE', line)

    def test_history_is_indexed_on_listened_at_and_per_track(self):
        self.assertIn('KEY `idx_listens_listened_at` (`listened_at`)', self.statement('scrobble_listens'))
        self.assertIn('KEY `idx_listens_track_user` (`track_id`,`username`)', self.statement('scrobble_listens'))
        self.assertIn('KEY `idx_unmatched_listened_at` (`listened_at`)', self.statement('scrobble_unmatched_listens'))


if __name__ == '__main__':
    unittest.main()
