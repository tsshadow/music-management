"""Coverage for /api/rules/genres advice: the analysis run and its summary.

What these pin down:

* a run reads the curator's own past work -- approved genres, corrections, the
  tagger page's artist and label links -- and rewrites `rules_genre_proposals`
  whole, without touching a decision;
* targets are stored with their id, so the page can post a decision without a
  second lookup;
* the queue endpoint in management.py carries the proposal per row and can be
  narrowed to one kind of advice.
"""

import json
import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')


import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.common.Helpers.GenreNameAnalyzer import REJECT, REWRITE, SPLIT
from services.music_manager.main import app
from services.music_manager.routers import genre_curation
from services.music_manager.routers import management as management_router
from services.music_manager.tests.scripted_cursor import (
    ScriptedCursor,
    assert_atomic,
    assert_rolled_back,
    transaction_log,
)

API_KEY = resolve_system_api_key()


class GenreCurationTestCase(unittest.TestCase):
    rules = ()

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.cursor = ScriptedCursor(self.rules)
        self.conn = MagicMock()
        self.conn.cursor.return_value = self.cursor
        for module in (genre_curation, management_router):
            patcher = patch.object(module, 'get_db_connection', return_value=self.conn)
            patcher.start()
            self.addCleanup(patcher.stop)

    def statements(self, fragment):
        return self.cursor.statements_matching(fragment)


class AnalyzeTest(GenreCurationTestCase):
    rules = (
        (
            "WHERE g.state = 'white' GROUP BY",
            None,
            [
                {'id': 1, 'name': 'Hardcore', 'tracks': 100},
                {'id': 2, 'name': 'Terror', 'tracks': 50},
                {'id': 3, 'name': 'Uptempo Hardcore', 'tracks': 80},
                {'id': 4, 'name': 'Frenchcore', 'tracks': 30},
            ],
        ),
        ('FROM rules_genre_expansions e', None, [{'name': 'uptempo', 'target': 'Uptempo Hardcore'}]),
        ("WHERE g.state = 'black' AND e.genre_id IS NULL", None, [{'name': 'HEARTBREAK'}]),
        (
            'FROM library_artists a',
            None,
            [{'name': 'Dr Peacock', 'genre': 'Frenchcore'}, {'name': 'Henry Fong', 'genre': None}],
        ),
        ('FROM library_labels l', None, []),
        (
            "WHERE state = 'unknown'",
            None,
            [
                {'id': 10, 'name': 'Hardcore/Terror'},
                {'id': 11, 'name': 'Upterror'},
                {'id': 12, 'name': 'henry fong'},
                {'id': 13, 'name': 'dr peacock'},
                {'id': 14, 'name': 'Tafelpoot'},
            ],
        ),
    )

    def run_analysis(self):
        response = self.client.post('/api/rules/genres/analyze', headers=self.headers)
        self.assertEqual(response.status_code, 202)
        job_id = response.json()['job_id']
        # TestClient runs BackgroundTasks before returning, so the job is done here.
        return self.client.get(f'/api/rules/genres/analyze/{job_id}', headers=self.headers).json()

    def test_a_run_rewrites_every_proposal_and_never_a_decision(self):
        status = self.run_analysis()
        self.assertEqual(status['status'], 'finished')
        self.assertEqual(status['total'], 5)
        self.assertEqual(status['summary'][SPLIT], 2)
        self.assertEqual(status['summary'][REWRITE], 1)
        self.assertEqual(status['summary'][REJECT], 2)
        self.assertTrue(self.statements('DELETE FROM rules_genre_proposals'))
        self.assertFalse(self.statements('UPDATE rules_genres'))
        self.assertFalse(self.statements('rules_genre_expansions (genre_id'))

    def test_targets_are_stored_with_their_ids(self):
        self.run_analysis()
        inserted = self.cursor.executed[-1]
        self.assertIn('INSERT INTO rules_genre_proposals', inserted[0])
        by_id = {row[0]: row for row in inserted[1]}
        self.assertEqual(json.loads(by_id[10][2]), [{'id': 1, 'name': 'Hardcore'}, {'id': 2, 'name': 'Terror'}])
        self.assertEqual(json.loads(by_id[11][2]), [{'id': 3, 'name': 'Uptempo Hardcore'}, {'id': 2, 'name': 'Terror'}])
        self.assertEqual(by_id[13][1], REWRITE)
        self.assertEqual(json.loads(by_id[13][2]), [{'id': 4, 'name': 'Frenchcore'}])
        self.assertEqual(json.loads(by_id[12][2]), [])
        self.assertIn('is an artist', json.loads(by_id[12][3])[0])

    def test_the_artist_lookup_skips_names_below_the_track_floor(self):
        self.run_analysis()
        statement, params = next(
            (statement, params) for statement, params in self.cursor.executed if 'FROM library_artists a' in statement
        )
        self.assertIn('>= %s OR r.id IS NOT NULL', statement)
        self.assertEqual(params, (genre_curation.MIN_ARTIST_TRACKS,))

    def test_a_second_request_while_one_runs_returns_the_same_job(self):
        genre_curation.job_store.jobs['genre-analysis-busy'] = {'status': 'running'}
        try:
            response = self.client.post('/api/rules/genres/analyze', headers=self.headers)
            self.assertEqual(response.json(), {'status': 'running', 'job_id': 'genre-analysis-busy'})
        finally:
            del genre_curation.job_store.jobs['genre-analysis-busy']

    def test_an_unknown_job_is_a_404(self):
        self.assertEqual(self.client.get('/api/rules/genres/analyze/nope', headers=self.headers).status_code, 404)


class AnalyzeWithoutDatabaseTest(unittest.TestCase):
    def test_a_missing_connection_fails_the_job_rather_than_the_request(self):
        client = TestClient(app)
        with patch.object(genre_curation, 'get_db_connection', return_value=None):
            response = client.post('/api/rules/genres/analyze', headers={'x-api-key': API_KEY})
            self.assertEqual(response.status_code, 202)
            status = client.get(
                f"/api/rules/genres/analyze/{response.json()['job_id']}", headers={'x-api-key': API_KEY}
            )
        self.assertEqual(status.json()['status'], 'failed')


class SummaryTest(GenreCurationTestCase):
    rules = (
        (
            'SELECT state, COUNT(*) AS n FROM rules_genres',
            None,
            [{'state': 'unknown', 'n': 821}, {'state': 'white', 'n': 271}],
        ),
        ('FROM rules_genre_proposals p', None, [{'kind': 'reject', 'n': 372}, {'kind': 'split', 'n': 172}]),
        ('MAX(analyzed_at)', None, {'analyzed_at': '2026-09-18 10:00:00'}),
    )

    def test_reports_the_size_of_the_job(self):
        body = self.client.get('/api/rules/genres/summary', headers=self.headers).json()
        self.assertEqual(body['unknown'], 821)
        self.assertEqual(body['white'], 271)
        self.assertEqual(body['black'], 0)
        self.assertEqual(body['proposals'], {'reject': 372, 'split': 172})
        self.assertEqual(body['analyzed_at'], '2026-09-18 10:00:00')

    def test_only_queued_genres_count_towards_the_proposal_totals(self):
        self.client.get('/api/rules/genres/summary', headers=self.headers)
        self.assertIn("WHERE g.state = 'unknown'", self.statements('FROM rules_genre_proposals p')[0][0])


class QueueWithProposalsTest(GenreCurationTestCase):
    rules = (
        (
            'FROM rules_genres g LEFT JOIN rules_genre_proposals p',
            None,
            [
                {
                    'id': 10,
                    'name': 'Hardcore/Terror',
                    'state': 'unknown',
                    'occurrences': 5,
                    'proposal_kind': 'split',
                    'proposal_targets': json.dumps([{'id': 1, 'name': 'Hardcore'}, {'id': 2, 'name': 'Terror'}]),
                    'proposal_evidence': json.dumps(['2 genres joined by a separator']),
                    'proposal_confidence': 90,
                },
                {
                    'id': 11,
                    'name': 'Fresh',
                    'state': 'unknown',
                    'occurrences': 1,
                    'proposal_kind': None,
                    'proposal_targets': None,
                    'proposal_evidence': None,
                    'proposal_confidence': None,
                },
            ],
        ),
    )

    def test_each_row_carries_its_proposal(self):
        body = self.client.get('/api/rules/genres?state=unknown', headers=self.headers).json()
        self.assertEqual(body[0]['proposal']['kind'], 'split')
        self.assertEqual([t['id'] for t in body[0]['proposal']['targets']], [1, 2])
        self.assertEqual(body[0]['proposal']['confidence'], 90)
        self.assertNotIn('proposal_kind', body[0])
        self.assertIsNone(body[1]['proposal'])

    def test_the_proposal_filter_narrows_the_query(self):
        self.client.get('/api/rules/genres?state=unknown&proposal=reject', headers=self.headers)
        statement, params = self.cursor.executed[0]
        self.assertIn('g.state = %s AND p.kind = %s', statement)
        self.assertEqual(params[:2], ['unknown', 'reject'])

    def test_an_unknown_proposal_kind_is_a_bad_request(self):
        response = self.client.get('/api/rules/genres?proposal=maybe', headers=self.headers)
        self.assertEqual(response.status_code, 400)


class TaggerGenreListTest(GenreCurationTestCase):
    def test_the_tagger_page_only_gets_approved_genres(self):
        self.client.get('/api/rules', headers=self.headers)
        self.assertIn("WHERE state = 'white'", self.statements('SELECT id, name, corrected_genre')[0][0])


class AnalyzeAtomicityTest(GenreCurationTestCase):
    """The proposals table is emptied and refilled in one transaction."""

    rules = AnalyzeTest.rules
    run_analysis = AnalyzeTest.run_analysis

    def test_the_delete_and_the_inserts_are_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        self.assertEqual(self.run_analysis()['status'], 'finished')
        assert_atomic(self, log, 'DELETE FROM rules_genre_proposals', 'INSERT INTO rules_genre_proposals')

    def test_a_failing_insert_keeps_the_previous_proposals(self):
        log = transaction_log(self.conn, self.cursor, fail_on='INSERT INTO rules_genre_proposals')
        self.assertEqual(self.run_analysis()['status'], 'failed')
        assert_rolled_back(self, log)


if __name__ == '__main__':
    unittest.main()
