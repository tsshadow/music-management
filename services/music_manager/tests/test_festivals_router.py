"""Coverage for /api/rules/festivals: the tagger's festival names, spellings and dates."""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils', 'DatabaseConnector', 'Cache')


import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.common.Helpers import Cache
from services.music_manager.main import app
from services.music_manager.routers import festivals
from services.music_manager.tests.scripted_cursor import (
    ScriptedCursor,
    assert_atomic,
    assert_rolled_back,
    transaction_log,
)

API_KEY = resolve_system_api_key()

FESTIVALS = [
    {'id': 1, 'name': 'Defqon.1', 'normalized_name': 'defqon 1', 'active': 1},
    {'id': 2, 'name': 'Karnaval Festival', 'normalized_name': 'karnaval festival', 'active': 1},
    {'id': 3, 'name': 'Intents', 'normalized_name': 'intents', 'active': 1},
    {'id': 4, 'name': 'Sunrise', 'normalized_name': 'sunrise', 'active': 0},
]
ALIASES = [
    {'festival_id': 1, 'alias': 'Defqon 1'},
    {'festival_id': 1, 'alias': 'Defqon.1 Weekend Festival'},
    {'festival_id': 3, 'alias': 'Intents Festival'},
]
EDITIONS = [{'festival_id': 1, 'year': 2025, 'date': '2025-06-27'}]


class FestivalTestCase(unittest.TestCase):
    rules = (
        ('FROM rules_festivals ORDER BY name', None, FESTIVALS),
        ('FROM rules_festival_aliases ORDER BY alias', None, ALIASES),
        ('FROM rules_festival_editions ORDER BY year', None, EDITIONS),
    )

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.cursor = ScriptedCursor(self.rules, lastrowid=9)
        self.conn = MagicMock()
        self.conn.cursor.return_value = self.cursor
        patcher = patch.object(festivals, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        Cache.reload.reset_mock()

    def reloaded(self):
        return [call.args[0] if call.args else None for call in Cache.reload.call_args_list]

    def statements(self, fragment):
        return self.cursor.statements_matching(fragment)


class ListTest(FestivalTestCase):
    def test_returns_every_festival_with_its_aliases_and_editions(self):
        body = self.client.get('/api/rules/festivals', headers=self.headers).json()
        by_name = {row['name']: row for row in body}
        self.assertEqual(by_name['Defqon.1']['aliases'], ['Defqon 1', 'Defqon.1 Weekend Festival'])
        self.assertEqual(by_name['Defqon.1']['editions'], [{'year': 2025, 'date': '2025-06-27'}])
        self.assertEqual(by_name['Karnaval Festival']['aliases'], [])
        self.assertIs(by_name['Sunrise']['active'], False)
        self.assertEqual(self.reloaded(), [])


class CreateTest(FestivalTestCase):
    def test_writes_the_festival_its_aliases_and_editions_and_refreshes_the_tagger(self):
        response = self.client.post(
            '/api/rules/festivals',
            json={
                'name': ' Dominator ',
                'aliases': ['Dominator Festival', 'dominator', '', 'DOMINATOR FESTIVAL'],
                'editions': [{'year': 2025, 'date': '2025-07-19'}, {'year': 2025, 'date': '2025-07-20'}],
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 201)
        self.assertEqual(response.json()['id'], 9)
        insert = self.statements('INSERT INTO rules_festivals')[0][1]
        self.assertEqual(insert, ('Dominator', 'dominator', 1))
        # The name itself and duplicates on the normalised key are not stored as aliases.
        aliases = [params[1] for _sql, params in self.statements('INSERT INTO rules_festival_aliases')]
        self.assertEqual(aliases, ['Dominator Festival'])
        editions = [params[1:] for _sql, params in self.statements('INSERT INTO rules_festival_editions')]
        self.assertEqual(editions, [(2025, '2025-07-20')])
        self.assertEqual(self.reloaded(), ['festivalHelper'])

    def test_a_bad_date_is_a_bad_request(self):
        response = self.client.post(
            '/api/rules/festivals',
            json={'name': 'Dominator', 'editions': [{'year': 2025, 'date': '19-07-2025'}]},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.statements('INSERT'))

    def test_an_empty_name_is_a_bad_request(self):
        self.assertEqual(
            self.client.post('/api/rules/festivals', json={'name': ' - '}, headers=self.headers).status_code, 400
        )


class DuplicateTest(FestivalTestCase):
    rules = FestivalTestCase.rules + (('WHERE normalized_name = %s', None, {'id': 1}),)

    def test_a_second_festival_with_the_same_key_is_a_conflict(self):
        response = self.client.post('/api/rules/festivals', json={'name': 'DEFQON 1'}, headers=self.headers)
        self.assertEqual(response.status_code, 409)


class UpdateTest(FestivalTestCase):
    rules = FestivalTestCase.rules + (('SELECT id FROM rules_festivals WHERE id = %s', None, {'id': 1}),)

    def test_replaces_the_children_wholesale(self):
        response = self.client.put(
            '/api/rules/festivals/1',
            json={'name': 'Defqon.1', 'active': False, 'aliases': ['Defqon'], 'editions': []},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.statements('UPDATE rules_festivals')[0][1], ('Defqon.1', 'defqon 1', 0, 1))
        self.assertTrue(self.statements('DELETE FROM rules_festival_aliases'))
        self.assertTrue(self.statements('DELETE FROM rules_festival_editions'))
        self.assertEqual([p[1] for _s, p in self.statements('INSERT INTO rules_festival_aliases')], ['Defqon'])
        self.assertEqual(self.reloaded(), ['festivalHelper'])


class UnknownUpdateTest(FestivalTestCase):
    def test_an_unknown_id_is_a_404(self):
        response = self.client.put('/api/rules/festivals/77', json={'name': 'X'}, headers=self.headers)
        self.assertEqual(response.status_code, 404)


class DeleteTest(FestivalTestCase):
    def test_removes_the_row_and_refreshes(self):
        self.assertEqual(self.client.delete('/api/rules/festivals/1', headers=self.headers).status_code, 200)
        self.assertEqual(self.reloaded(), ['festivalHelper'])

    def test_a_missing_row_is_a_404(self):
        self.cursor.rowcount = 0
        self.assertEqual(self.client.delete('/api/rules/festivals/1', headers=self.headers).status_code, 404)


class ProbeTest(FestivalTestCase):
    def test_says_what_the_saved_rules_recognise(self):
        body = self.client.post(
            '/api/rules/festivals/probe',
            json={'text': 'Angerfist @ Intents Karnaval Festival 2025'},
            headers=self.headers,
        ).json()
        self.assertEqual([m['festival'] for m in body['matches']], ['Karnaval Festival'])
        self.assertEqual(body['matches'][0]['year'], 2025)

    def test_an_edition_date_comes_along(self):
        body = self.client.post(
            '/api/rules/festivals/probe', json={'text': 'Defqon 1 2025 - RED'}, headers=self.headers
        ).json()
        self.assertEqual(body['matches'][0], {'festival': 'Defqon.1', 'year': 2025, 'date': '2025-06-27'})

    def test_an_inactive_festival_does_not_match(self):
        body = self.client.post(
            '/api/rules/festivals/probe', json={'text': 'Sunrise 2024'}, headers=self.headers
        ).json()
        self.assertEqual(body['matches'], [])


class FestivalAtomicityTest(FestivalTestCase):
    """A festival's aliases and editions are deleted and re-inserted in one transaction."""

    rules = UpdateTest.rules

    def update(self):
        return self.client.put(
            '/api/rules/festivals/1',
            json={'name': 'Defqon.1', 'aliases': ['Defqon'], 'editions': [{'year': 2025, 'date': '2025-06-27'}]},
            headers=self.headers,
        )

    def test_the_children_are_replaced_inside_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        self.assertEqual(self.update().status_code, 200)
        assert_atomic(
            self,
            log,
            'UPDATE rules_festivals',
            'DELETE FROM rules_festival_aliases',
            'INSERT INTO rules_festival_aliases',
            'DELETE FROM rules_festival_editions',
            'INSERT INTO rules_festival_editions',
        )

    def test_a_failing_insert_rolls_the_delete_back(self):
        log = transaction_log(self.conn, self.cursor, fail_on='INSERT INTO rules_festival_editions')
        with self.assertRaises(RuntimeError):
            self.update()
        assert_rolled_back(self, log)
        self.assertEqual(self.reloaded(), [])

    def test_a_new_festival_and_its_children_are_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        response = self.client.post(
            '/api/rules/festivals', json={'name': 'Dominator', 'aliases': ['Dominator Festival']}, headers=self.headers
        )
        self.assertEqual(response.status_code, 201)
        assert_atomic(
            self,
            log,
            'INSERT INTO rules_festivals',
            'DELETE FROM rules_festival_aliases',
            'INSERT INTO rules_festival_aliases',
        )


if __name__ == '__main__':
    unittest.main()
