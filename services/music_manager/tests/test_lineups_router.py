"""Coverage for /api/rules/lineups: the lineup files, and the match report before a write."""

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import pytest

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils', 'DatabaseConnector')


import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers import lineups

API_KEY = resolve_system_api_key()
KNOWN = ['Angerfist', 'D-Block & S-te-Fan', 'Miss K8']


class LineupTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)
        for patcher in (
            patch.object(lineups, 'LINEUP_DIR', self.tmp.name),
            patch.object(lineups, 'known_artists', return_value=KNOWN),
        ):
            patcher.start()
            self.addCleanup(patcher.stop)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')


class ListTest(LineupTestCase):
    def test_lists_every_file_as_the_id_the_browse_pages_use(self):
        self.write('Defqon.1/2014/RED.txt', 'Angerfist\nMiss K8\n')
        self.write('Intents 2025.txt', 'Angerfist\n')
        body = self.client.get('/api/rules/lineups', headers=self.headers).json()
        self.assertEqual(
            body['lineups'],
            [
                {'id': 'Defqon.1/2014/RED', 'festival': 'Defqon.1', 'year': '2014', 'stage': 'RED', 'artists': 2},
                {'id': 'Intents 2025', 'festival': 'Intents 2025', 'year': None, 'stage': None, 'artists': 1},
            ],
        )

    def test_an_absent_directory_is_an_empty_list(self):
        with patch.object(lineups, 'LINEUP_DIR', str(self.root / 'nowhere')):
            body = self.client.get('/api/rules/lineups', headers=self.headers).json()
        self.assertEqual(body['lineups'], [])


class ReadTest(LineupTestCase):
    def test_reports_what_the_library_can_match(self):
        self.write('Defqon.1/2014/RED.txt', 'Angerfist\nD-Block and S-te-fan\n')
        body = self.client.get('/api/rules/lineups/Defqon.1/2014/RED', headers=self.headers).json()
        self.assertEqual(body['names'], ['Angerfist', 'D-Block and S-te-fan'])
        self.assertEqual(body['match']['matched'], ['Angerfist'])
        self.assertEqual(body['match']['unmatched'], ['D-Block and S-te-fan'])
        self.assertEqual(body['match']['suggestions'], {'D-Block and S-te-fan': ['D-Block & S-te-Fan']})

    def test_a_missing_lineup_is_a_404(self):
        self.assertEqual(self.client.get('/api/rules/lineups/Nope/2020', headers=self.headers).status_code, 404)

    def test_a_path_that_leaves_the_directory_is_refused(self):
        response = self.client.get('/api/rules/lineups/../../etc/passwd', headers=self.headers)
        self.assertIn(response.status_code, (400, 404))
        self.assertNotIn('root:', response.text)


class WriteTest(LineupTestCase):
    def test_writes_the_file_in_the_library_spelling_where_it_matches(self):
        response = self.client.put(
            '/api/rules/lineups',
            json={
                'festival': 'Defqon.1',
                'year': 2025,
                'stage': 'RED',
                'text': 'angerfist\n\nMiss K8\nNobody\n12:00\n',
            },
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['id'], 'Defqon.1/2025/RED')
        self.assertEqual(body['names'], ['Angerfist', 'Miss K8', 'Nobody'])
        self.assertEqual(body['match']['unmatched'], ['Nobody'])
        self.assertEqual((self.root / 'Defqon.1/2025/RED.txt').read_text(), 'Angerfist\nMiss K8\nNobody\n')

    def test_a_stage_without_a_year_is_a_bad_request(self):
        response = self.client.put(
            '/api/rules/lineups',
            json={'festival': 'Defqon.1', 'stage': 'RED', 'text': 'Angerfist'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)

    def test_an_empty_bill_is_a_bad_request(self):
        response = self.client.put(
            '/api/rules/lineups', json={'festival': 'Defqon.1', 'year': 2025, 'text': '\n12:00\n'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 400)

    def test_a_festival_name_with_a_slash_stays_one_directory(self):
        response = self.client.put(
            '/api/rules/lineups',
            json={'festival': 'Q-BASE/Q-dance', 'year': 2010, 'text': 'Angerfist'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue((self.root / 'Q-BASE-Q-dance/2010.txt').is_file())


class MatchTest(LineupTestCase):
    def test_previews_a_pasted_bill_without_writing(self):
        body = self.client.post(
            '/api/rules/lineups/match', json={'text': 'Angerfist\nOutsiders'}, headers=self.headers
        ).json()
        self.assertEqual(body['match']['matched'], ['Angerfist'])
        self.assertEqual(body['match']['unmatched'], ['Outsiders'])
        self.assertEqual(list(self.root.iterdir()), [])


class DeleteTest(LineupTestCase):
    def test_removes_the_file_and_the_directories_it_leaves_empty(self):
        self.write('Defqon.1/2014/RED.txt', 'Angerfist\n')
        self.write('Defqon.1/2015.txt', 'Angerfist\n')
        self.assertEqual(
            self.client.delete('/api/rules/lineups/Defqon.1/2014/RED', headers=self.headers).status_code, 200
        )
        self.assertFalse((self.root / 'Defqon.1/2014').exists())
        self.assertTrue((self.root / 'Defqon.1/2015.txt').is_file())

    def test_a_missing_file_is_a_404(self):
        self.assertEqual(self.client.delete('/api/rules/lineups/Nope', headers=self.headers).status_code, 404)


if __name__ == '__main__':
    unittest.main()
