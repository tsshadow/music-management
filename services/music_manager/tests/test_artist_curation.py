"""Coverage for /api/rules/artists: the artist curation queue.

What these pin down, beyond the CRUD:

* a decision is mirrored into `rules_ignored_artists` -- the table the tagger reads --
  and the preloaded helper is refreshed, or the running tagger keeps the old answer;
* a correction approves its target in the same call, and never points at a rejected
  name;
* the proposal logic is pure and testable on a dict: collisions resolve to the spelling
  with the most tracks, and a rewrite towards a smaller name is downgraded, because
  that is the direction the dry run kept getting wrong.
"""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector', 'Cache')


import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.common.Helpers import Cache
from services.common.Helpers.ArtistNameAnalyzer import REJECT, REWRITE, UNKNOWN
from services.music_manager.main import app
from services.music_manager.routers import artist_curation
from services.music_manager.tests.scripted_cursor import (
    ScriptedCursor,
    assert_atomic,
    assert_rolled_back,
    transaction_log,
)

API_KEY = resolve_system_api_key()


class ProposeAllTest(unittest.TestCase):
    def test_collisions_resolve_to_the_spelling_with_the_most_tracks(self):
        targets = artist_curation.collision_targets({'Dr. Peacock': 816, 'Dr.Peacock': 10, 'dr peacock': 3})
        self.assertEqual(targets, {'Dr.Peacock': 'Dr. Peacock', 'dr peacock': 'Dr. Peacock'})

    def test_a_tie_picks_the_shortest_then_alphabetical_spelling(self):
        self.assertEqual(artist_curation.collision_targets({'Rbr': 5, 'RBR ©': 5}), {'RBR ©': 'Rbr'})
        self.assertEqual(artist_curation.collision_targets({'a': 5, 'A': 5}), {'a': 'A'})

    def test_names_alone_in_their_group_are_not_targets(self):
        self.assertEqual(artist_curation.collision_targets({'Angerfist': 100, 'Miss K8': 40}), {})

    def test_a_collision_becomes_a_rewrite_with_the_counts_as_evidence(self):
        proposals = artist_curation.propose_all({'Dr. Peacock': 816, 'Dr.Peacock': 10}, approved=[])
        self.assertEqual(proposals['Dr.Peacock'].kind, REWRITE)
        self.assertEqual(proposals['Dr.Peacock'].values, ['Dr. Peacock'])
        self.assertIn('816 tracks against 10', proposals['Dr.Peacock'].evidence[0])
        # The winner is not rewritten to anything.
        self.assertNotEqual(proposals['Dr. Peacock'].kind, REWRITE)

    def test_an_approved_name_rescues_its_polluted_variant(self):
        proposals = artist_curation.propose_all(
            {'**FREE DOWNLOAD** Angerfist': 2}, approved=['Angerfist'], counts={'Angerfist': 300}
        )
        proposal = proposals['**FREE DOWNLOAD** Angerfist']
        self.assertEqual(proposal.kind, REWRITE)
        self.assertEqual(proposal.values, ['Angerfist'])

    def test_an_approved_target_outside_the_library_is_still_a_rewrite(self):
        proposals = artist_curation.propose_all({'angerfist': 2}, approved=['Angerfist'])
        self.assertEqual(proposals['angerfist'].kind, REWRITE)

    def test_a_rewrite_towards_a_smaller_name_is_downgraded(self):
        """`Dr. Peacock` (816) must never be rewritten to an approved `Dr.Peacock` (10)."""
        proposals = artist_curation.propose_all(
            {'Dr. Peacock': 816}, approved=['Dr.Peacock'], counts={'Dr.Peacock': 10}
        )
        proposal = proposals['Dr. Peacock']
        self.assertEqual(proposal.kind, UNKNOWN)
        self.assertEqual(proposal.values, ['Dr. Peacock'])
        self.assertTrue(any('fewer tracks' in line for line in proposal.evidence))

    def test_a_dj_prefix_merges_into_the_bare_name_with_the_most_tracks(self):
        proposals = artist_curation.propose_all(
            {'Angerfist': 300, 'DJ Angerfist': 5, 'MC Tha Watcher': 2, 'Tha Watcher': 40}, approved=[]
        )
        self.assertEqual(proposals['DJ Angerfist'].values, ['Angerfist'])
        self.assertIn('without the DJ/MC prefix', proposals['DJ Angerfist'].evidence[0])
        self.assertEqual(proposals['MC Tha Watcher'].values, ['Tha Watcher'])
        self.assertNotEqual(proposals['Angerfist'].kind, REWRITE)

    def test_a_dj_prefix_on_an_approved_name_is_advice_to_merge(self):
        proposals = artist_curation.propose_all({'DJ Angerfist': 5}, approved=['Angerfist'], counts={'Angerfist': 300})
        self.assertEqual(proposals['DJ Angerfist'].kind, REWRITE)
        self.assertEqual(proposals['DJ Angerfist'].values, ['Angerfist'])

    def test_a_prefix_with_nothing_to_merge_into_is_left_alone(self):
        proposals = artist_curation.propose_all({'DJ Mag': 50}, approved=['Angerfist'])
        self.assertEqual(proposals['DJ Mag'].kind, UNKNOWN)

    def test_shape_alone_still_rejects_what_cannot_be_a_name(self):
        proposals = artist_curation.propose_all({'***': 1, 'Angerfist': 5}, approved=[])
        self.assertEqual(proposals['***'].kind, REJECT)
        self.assertEqual(proposals['Angerfist'].kind, UNKNOWN)


class ArtistCurationTestCase(unittest.TestCase):
    rules = ()

    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.cursor = ScriptedCursor(self.rules)
        self.conn = MagicMock()
        self.conn.cursor.return_value = self.cursor
        patcher = patch.object(artist_curation, 'get_db_connection', return_value=self.conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        invalidate = patch.object(artist_curation, 'invalidate_quietly', return_value=0)
        self.invalidate = invalidate.start()
        self.addCleanup(invalidate.stop)
        Cache.reload.reset_mock()

    def reloaded_helpers(self):
        return [call.args[0] if call.args else None for call in Cache.reload.call_args_list]

    def statements(self, fragment):
        return self.cursor.statements_matching(fragment)


class ListTest(ArtistCurationTestCase):
    rules = (
        ('SELECT COUNT(*) AS total', None, {'total': 2}),
        (
            'FROM library_artists a LEFT JOIN rules_artists r',
            None,
            [
                {
                    'id': 1,
                    'name': 'Premiere',
                    'track_count': 9180,
                    'state': None,
                    'canonical_name': None,
                    'decided_at': None,
                    'decided_by': None,
                    'proposal_kind': 'reject',
                    'proposal_target': None,
                    'proposal_evidence': '["nothing left after removing noise"]',
                    'proposal_confidence': 95,
                },
                {
                    'id': 2,
                    'name': 'Angerfist',
                    'track_count': 300,
                    'state': None,
                    'canonical_name': None,
                    'decided_at': None,
                    'decided_by': None,
                    'proposal_kind': None,
                    'proposal_target': None,
                    'proposal_evidence': None,
                    'proposal_confidence': None,
                },
            ],
        ),
    )

    def test_the_queue_is_the_undecided_names_with_their_proposals(self):
        response = self.client.get('/api/rules/artists', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['total'], 2)
        self.assertEqual(body['rows'][0]['name'], 'Premiere')
        self.assertEqual(body['rows'][0]['state'], 'unknown')
        self.assertEqual(body['rows'][0]['proposal_evidence'], ['nothing left after removing noise'])
        self.assertEqual(body['rows'][1]['proposal_evidence'], [])
        where = self.statements('FROM library_artists a LEFT JOIN rules_artists r')[-1][0]
        self.assertIn('r.name IS NULL', where)

    def test_the_pending_filter_is_the_queue_minus_the_grandfathered_names(self):
        """Pending is what the tagger does not trust: undecided and not grandfathered."""
        response = self.client.get('/api/rules/artists?state=pending', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['rows'][0]['pending'], False)
        sql = self.statements('FROM library_artists a LEFT JOIN rules_artists r')[-1][0]
        self.assertIn('LEFT JOIN rules_artist_legacy_trust l ON l.name = a.name', sql)
        self.assertIn('WHERE r.name IS NULL AND l.name IS NULL', sql)

    def test_a_decided_state_lists_from_the_decision_table(self):
        self.client.get('/api/rules/artists?state=black', headers=self.headers)
        self.assertTrue(self.statements('FROM rules_artists r LEFT JOIN library_artists a'))

    def test_search_and_proposal_filters_reach_the_query(self):
        self.client.get('/api/rules/artists?q=peac&proposal=rewrite', headers=self.headers)
        sql, params = self.statements('FROM library_artists a LEFT JOIN rules_artists r')[-1]
        self.assertIn('LIKE %s', sql)
        self.assertIn('p.kind = %s', sql)
        self.assertEqual(params[:2], ['%peac%', 'rewrite'])

    def test_unknown_filters_are_a_bad_request(self):
        self.assertEqual(self.client.get('/api/rules/artists?state=grey', headers=self.headers).status_code, 400)
        self.assertEqual(self.client.get('/api/rules/artists?proposal=maybe', headers=self.headers).status_code, 400)
        self.assertEqual(self.client.get('/api/rules/artists?sort=age', headers=self.headers).status_code, 400)

    def test_the_limit_is_capped(self):
        self.client.get('/api/rules/artists?limit=100000', headers=self.headers)
        _sql, params = self.statements('LIMIT %s OFFSET %s')[-1]
        self.assertEqual(params[-2], artist_curation.MAX_LIMIT)

    def test_reading_does_not_reload_the_tagger_caches(self):
        self.client.get('/api/rules/artists', headers=self.headers)
        self.assertEqual(self.reloaded_helpers(), [])


class RejectTest(ArtistCurationTestCase):
    def test_rejecting_records_the_decision_and_mirrors_it_to_the_tagger(self):
        response = self.client.post(
            '/api/rules/artists/decide',
            json={'names': ['Premiere', ' Premiere ', 'OUT NOW'], 'state': 'black'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['decided'], 2)
        decisions = self.statements('INSERT INTO rules_artists')
        self.assertEqual([params[:2] for _sql, params in decisions], [('Premiere', 'black'), ('OUT NOW', 'black')])
        mirrored = self.statements('INSERT INTO rules_ignored_artists')
        self.assertEqual([params for _sql, params in mirrored], [('Premiere', None), ('OUT NOW', None)])
        self.assertEqual(self.reloaded_helpers(), ['rules_ignored_artists', 'library_artists'])
        self.assertEqual([call.args[0] for call in self.invalidate.call_args_list], ['Premiere', 'OUT NOW'])
        # Exact, not the wide term match: a rejected '001' must not retag every catalogue number.
        self.assertTrue(all(call.kwargs.get('exact') for call in self.invalidate.call_args_list))

    def test_who_decided_is_recorded(self):
        self.client.post(
            '/api/rules/artists/decide', json={'names': ['Premiere'], 'state': 'black'}, headers=self.headers
        )
        params = self.statements('INSERT INTO rules_artists')[0][1]
        self.assertEqual(params[3], 'system')

    def test_the_system_key_may_sign_as_a_script(self):
        self.client.post(
            '/api/rules/artists/decide',
            json={'names': ['Premiere'], 'state': 'black', 'decided_by': 'auto-external'},
            headers=self.headers,
        )
        params = self.statements('INSERT INTO rules_artists')[0][1]
        self.assertEqual(params[3], 'auto-external')


class ApproveTest(ArtistCurationTestCase):
    rules = (('SELECT id FROM rules_ignored_artists', None, {'id': 4}),)

    def test_approving_removes_any_redirect_the_tagger_held(self):
        response = self.client.post(
            '/api/rules/artists/decide', json={'names': ['Angerfist'], 'state': 'white'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(self.statements('INSERT INTO rules_artists')[0][1][:2], ('Angerfist', 'white'))
        self.assertTrue(self.statements('DELETE FROM rules_ignored_artists'))
        self.assertFalse(self.statements('INSERT INTO rules_ignored_artists'))
        self.assertEqual(self.reloaded_helpers(), ['rules_ignored_artists', 'library_artists'])
        # Nothing in a file changes on an approval, so nothing is marked for retag.
        self.assertEqual(self.invalidate.call_count, 0)

    def test_an_approval_cannot_carry_a_correction(self):
        response = self.client.post(
            '/api/rules/artists/decide',
            json={'names': ['Angerfist'], 'state': 'white', 'canonical_name': 'Angerfist!'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)


class CorrectTest(ArtistCurationTestCase):
    def test_a_correction_approves_its_target_in_the_same_call(self):
        response = self.client.post(
            '/api/rules/artists/decide',
            json={'names': ['Dr.Peacock'], 'state': 'black', 'canonical_name': 'Dr. Peacock'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        decisions = [params[:3] for _sql, params in self.statements('INSERT INTO rules_artists')]
        self.assertEqual(decisions, [('Dr. Peacock', 'white', None), ('Dr.Peacock', 'black', 'Dr. Peacock')])
        mirrored = [params for _sql, params in self.statements('INSERT INTO rules_ignored_artists')]
        self.assertEqual(mirrored, [('Dr.Peacock', 'Dr. Peacock')])

    def test_a_name_cannot_be_its_own_correction(self):
        response = self.client.post(
            '/api/rules/artists/decide',
            json={'names': ['Angerfist'], 'state': 'black', 'canonical_name': 'angerfist'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)


class CorrectToRejectedTest(ArtistCurationTestCase):
    rules = (('SELECT state FROM rules_artists WHERE name', None, {'state': 'black'}),)

    def test_a_rejected_target_is_refused(self):
        response = self.client.post(
            '/api/rules/artists/decide',
            json={'names': ['Dr.Peacock'], 'state': 'black', 'canonical_name': 'Premiere'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(self.statements('INSERT INTO rules_artists'))


class DecisionValidationTest(ArtistCurationTestCase):
    def test_empty_and_oversized_requests_are_bad_requests(self):
        self.assertEqual(
            self.client.post(
                '/api/rules/artists/decide', json={'names': [' '], 'state': 'black'}, headers=self.headers
            ).status_code,
            400,
        )
        too_many = [f'name {i}' for i in range(artist_curation.MAX_DECISION_NAMES + 1)]
        self.assertEqual(
            self.client.post(
                '/api/rules/artists/decide', json={'names': too_many, 'state': 'black'}, headers=self.headers
            ).status_code,
            400,
        )
        self.assertEqual(
            self.client.post(
                '/api/rules/artists/decide', json={'names': ['x'], 'state': 'grey'}, headers=self.headers
            ).status_code,
            400,
        )


class UndoTest(ArtistCurationTestCase):
    def test_forgetting_a_decision_clears_both_tables(self):
        response = self.client.delete('/api/rules/artists/Dr.Peacock', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertTrue(self.statements('DELETE FROM rules_artists'))
        self.assertTrue(self.statements('DELETE FROM rules_ignored_artists'))
        self.assertEqual(self.reloaded_helpers(), ['rules_ignored_artists', 'library_artists'])
        self.assertEqual(response.json()['returned_to_queue'], [])

    def test_a_name_without_a_decision_is_a_404(self):
        self.cursor.rowcount = 0
        log = transaction_log(self.conn, self.cursor)
        self.assertEqual(self.client.delete('/api/rules/artists/Nobody', headers=self.headers).status_code, 404)
        # Nothing else is touched on the way to that 404.
        assert_rolled_back(self, log)
        self.assertFalse(self.statements('DELETE FROM rules_ignored_artists'))


#: What `_redirect_dependents` finds pointing at the name being decided.
DEPENDENTS = ('UNION SELECT name FROM rules_ignored_artists', None, [{'name': 'Angerfst'}, {'name': 'Angerfist!'}])


class UndoWithRedirectsTest(ArtistCurationTestCase):
    """Bug 080: undoing X left `Y -> X` rows pointing at a name nobody approved any more."""

    rules = (DEPENDENTS,)

    def test_redirects_to_the_undone_name_go_back_to_the_queue_with_it(self):
        log = transaction_log(self.conn, self.cursor)
        response = self.client.delete('/api/rules/artists/Angerfist', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['returned_to_queue'], ['Angerfist!', 'Angerfst'])
        requeue = self.statements('DELETE FROM rules_artists WHERE state = %s AND LOWER(canonical_name)')
        self.assertEqual(requeue[0][1], ('black', 'Angerfist'))
        self.assertTrue(self.statements('DELETE FROM rules_ignored_artists WHERE LOWER(corrected_name)'))
        assert_atomic(self, log, 'DELETE FROM rules_artists', 'DELETE FROM rules_ignored_artists')


class RejectWithRedirectsTest(ArtistCurationTestCase):
    rules = (DEPENDENTS,)

    def test_rejecting_with_a_correction_repoints_the_redirects_to_it(self):
        log = transaction_log(self.conn, self.cursor)
        response = self.client.post(
            '/api/rules/artists/decide',
            json={'names': ['Angerfist'], 'state': 'black', 'canonical_name': 'Angerfist (NL)'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertEqual(body['repointed'], ['Angerfist!', 'Angerfst'])
        self.assertEqual(body['returned_to_queue'], [])
        decisions = self.statements('UPDATE rules_artists SET canonical_name')
        self.assertEqual(decisions[0][1], ('Angerfist (NL)', 'black', 'Angerfist', 'Angerfist (NL)'))
        mirrored = self.statements('UPDATE rules_ignored_artists SET corrected_name = %s WHERE LOWER(corrected_name)')
        self.assertEqual(mirrored[0][1], ('Angerfist (NL)', 'Angerfist', 'Angerfist (NL)'))
        # Nothing is thrown away when the chain can be collapsed.
        self.assertFalse(self.statements('DELETE FROM rules_artists'))
        assert_atomic(self, log, 'UPDATE rules_artists', 'INSERT INTO rules_artists')

    def test_rejecting_without_a_correction_returns_the_redirects_to_the_queue(self):
        response = self.client.post(
            '/api/rules/artists/decide', json={'names': ['Angerfist'], 'state': 'black'}, headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['returned_to_queue'], ['Angerfist!', 'Angerfst'])
        self.assertTrue(self.statements('DELETE FROM rules_artists WHERE state = %s AND LOWER(canonical_name)'))
        self.assertFalse(self.statements('UPDATE rules_artists SET canonical_name'))
        # They are not rejected in its wake: a plain rejection would strip the credit.
        rejected = [params[0] for _sql, params in self.statements('INSERT INTO rules_artists')]
        self.assertEqual(rejected, ['Angerfist'])

    def test_a_dependent_decided_in_the_same_call_is_not_reported_twice(self):
        response = self.client.post(
            '/api/rules/artists/decide',
            json={'names': ['Angerfist', 'Angerfst'], 'state': 'black'},
            headers=self.headers,
        )
        self.assertEqual(response.json()['returned_to_queue'], ['Angerfist!'])

    def test_approving_leaves_the_redirects_alone(self):
        self.client.post(
            '/api/rules/artists/decide', json={'names': ['Angerfist'], 'state': 'white'}, headers=self.headers
        )
        self.assertFalse(self.statements('UNION SELECT name FROM rules_ignored_artists'))


class CorrectToRejectedIsNotATransactionTest(ArtistCurationTestCase):
    rules = (('SELECT state FROM rules_artists WHERE name', None, {'state': 'black'}),)

    def test_a_refused_target_never_opens_a_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        response = self.client.post(
            '/api/rules/artists/decide',
            json={'names': ['Dr.Peacock'], 'state': 'black', 'canonical_name': 'Premiere'},
            headers=self.headers,
        )
        self.assertEqual(response.status_code, 400)
        self.assertNotIn('BEGIN', log)


class RedirectIssuesPureTest(unittest.TestCase):
    def test_a_clean_table_has_no_issues(self):
        report = artist_curation.find_redirect_issues(
            [('Dr.Peacock', 'Dr. Peacock'), ('Premiere', None)],
            [
                {'name': 'Dr. Peacock', 'state': 'white', 'canonical_name': None, 'decided_by': 'user'},
                {'name': 'Dr.Peacock', 'state': 'black', 'canonical_name': 'Dr. Peacock', 'decided_by': 'user'},
            ],
        )
        self.assertEqual(report, {'count': 0, 'dangling': [], 'cycles': [], 'chains': []})

    def test_a_redirect_to_a_rejected_or_dropped_name_is_dangling(self):
        report = artist_curation.find_redirect_issues(
            [('Y', 'Premiere'), ('Premiere', None), ('W', 'OUT NOW')],
            [{'name': 'OUT NOW', 'state': 'black', 'canonical_name': None, 'decided_by': 'user'}],
        )
        self.assertEqual(
            [(row['name'], row['reason']) for row in report['dangling']],
            [('W', 'target is rejected'), ('Y', 'target is dropped by the tagger')],
        )
        self.assertEqual(report['count'], 2)

    def test_a_page_redirect_whose_target_was_undone_is_dangling_but_a_legacy_one_is_not(self):
        report = artist_curation.find_redirect_issues(
            [('Angerfst', 'Angerfist'), ('Ran D', 'Ran-D')],
            [
                {'name': 'Angerfst', 'state': 'black', 'canonical_name': 'Angerfist', 'decided_by': 'user'},
                {'name': 'Ran D', 'state': 'black', 'canonical_name': 'Ran-D', 'decided_by': 'legacy-redirect'},
            ],
        )
        self.assertEqual([row['name'] for row in report['dangling']], ['Angerfst'])

    def test_a_chain_ending_at_a_rejected_name_is_dangling_with_its_path(self):
        report = artist_curation.find_redirect_issues(
            [('Y', 'X'), ('X', 'Z')],
            [{'name': 'Z', 'state': 'black', 'canonical_name': None, 'decided_by': 'user'}],
        )
        dangling = {row['name']: row for row in report['dangling']}
        self.assertEqual(dangling['Y']['path'], ['Y', 'X', 'Z'])
        self.assertEqual(report['chains'], [{'name': 'Y', 'path': ['Y', 'X', 'Z']}])

    def test_a_loop_is_reported_and_its_members_are_not_also_dangling(self):
        report = artist_curation.find_redirect_issues([('A', 'B'), ('B', 'A')], [])
        self.assertEqual(report['cycles'], [['A', 'B']])
        self.assertEqual(report['dangling'], [])
        self.assertEqual(report['count'], 1)

    def test_an_unmirrored_curation_redirect_still_counts(self):
        report = artist_curation.find_redirect_issues(
            [],
            [
                {'name': 'A', 'state': 'black', 'canonical_name': 'B', 'decided_by': 'user'},
                {'name': 'B', 'state': 'black', 'canonical_name': 'A', 'decided_by': 'user'},
            ],
        )
        self.assertEqual(report['cycles'], [['A', 'B']])


class RedirectIssuesEndpointTest(ArtistCurationTestCase):
    rules = (
        ('SELECT name, corrected_name FROM rules_ignored_artists', None, [{'name': 'Y', 'corrected_name': 'X'}]),
        (
            'SELECT name, state, canonical_name, decided_by FROM rules_artists',
            None,
            [{'name': 'X', 'state': 'black', 'canonical_name': None, 'decided_by': 'user'}],
        ),
    )

    def test_the_report_reads_both_tables_and_writes_nothing(self):
        response = self.client.get('/api/rules/artists/redirects/issues', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()['dangling'][0]['name'], 'Y')
        self.assertTrue(all(sql.startswith('SELECT') for sql, _params in self.cursor.executed))
        self.assertEqual(self.reloaded_helpers(), [])


class SummaryTest(ArtistCurationTestCase):
    rules = (
        ('SELECT COUNT(*) AS n FROM library_artists', None, {'n': 46885}),
        ('SELECT state, COUNT(*) AS n FROM rules_artists', None, [{'state': 'black', 'n': 2658}]),
        # Before the plain "r.name IS NULL" rule: the proposal count carries that clause too.
        ('FROM rules_artist_proposals p', None, [{'kind': 'reject', 'n': 267}]),
        ('WHERE r.name IS NULL', None, {'n': 44227}),
        ('MAX(analyzed_at)', None, {'analyzed_at': '2026-09-16 04:00:00'}),
    )

    def test_reports_the_size_of_the_job(self):
        body = self.client.get('/api/rules/artists/summary', headers=self.headers).json()
        self.assertEqual(body['in_library'], 46885)
        self.assertEqual(body['black'], 2658)
        self.assertEqual(body['white'], 0)
        self.assertEqual(body['proposals'], {'reject': 267})
        self.assertEqual(body['analyzed_at'], '2026-09-16 04:00:00')


class AnalyzeTest(ArtistCurationTestCase):
    rules = (
        ('FROM rules_artists WHERE state', None, [{'name': 'Angerfist'}]),
        (
            'WHERE r.name IS NULL',
            None,
            [
                {'name': 'Premiere', 'track_count': 9180},
                {'name': '**FREE DOWNLOAD** Angerfist', 'track_count': 2},
                {'name': 'Dr. Peacock', 'track_count': 816},
                {'name': 'Dr.Peacock', 'track_count': 10},
            ],
        ),
        ('WHERE a.name IN', None, [{'name': 'Angerfist', 'track_count': 300}]),
    )

    def test_a_run_rewrites_every_proposal_and_never_a_decision(self):
        response = self.client.post('/api/rules/artists/analyze', headers=self.headers)
        self.assertEqual(response.status_code, 202)
        job_id = response.json()['job_id']
        # TestClient runs BackgroundTasks before returning, so the job is done here.
        status = self.client.get(f'/api/rules/artists/analyze/{job_id}', headers=self.headers).json()
        self.assertEqual(status['status'], 'finished')
        self.assertEqual(status['summary']['reject'], 1)
        self.assertEqual(status['summary']['rewrite'], 2)
        self.assertTrue(self.statements('DELETE FROM rules_artist_proposals'))
        self.assertFalse(self.statements('INSERT INTO rules_artists'))
        self.assertFalse(self.statements('DELETE FROM rules_artists'))
        inserted = self.cursor.executed[-1]
        self.assertIn('INSERT INTO rules_artist_proposals', inserted[0])

    def test_an_unknown_job_is_a_404(self):
        self.assertEqual(self.client.get('/api/rules/artists/analyze/nope', headers=self.headers).status_code, 404)


class AnalyzeAtomicityTest(ArtistCurationTestCase):
    """The proposals table is emptied and refilled in one transaction."""

    rules = AnalyzeTest.rules

    def run_analysis(self):
        job_id = self.client.post('/api/rules/artists/analyze', headers=self.headers).json()['job_id']
        return self.client.get(f'/api/rules/artists/analyze/{job_id}', headers=self.headers).json()

    def test_the_delete_and_the_inserts_are_one_transaction(self):
        log = transaction_log(self.conn, self.cursor)
        self.assertEqual(self.run_analysis()['status'], 'finished')
        assert_atomic(self, log, 'DELETE FROM rules_artist_proposals', 'INSERT INTO rules_artist_proposals')

    def test_a_failing_insert_keeps_the_previous_proposals(self):
        log = transaction_log(self.conn, self.cursor, fail_on='INSERT INTO rules_artist_proposals')
        self.assertEqual(self.run_analysis()['status'], 'failed')
        assert_rolled_back(self, log)


if __name__ == '__main__':
    unittest.main()


class AutoApproveReviewListTest(ArtistCurationTestCase):
    """The scheduled evidence run's approvals are reviewable: filter by decider, newest first."""

    rules = (('SELECT COUNT(*) AS total', None, {'total': 0}),)

    def test_decided_by_and_the_decided_sort_reach_the_query(self):
        response = self.client.get(
            '/api/rules/artists?state=white&decided_by=auto-external&sort=decided', headers=self.headers
        )
        self.assertEqual(response.status_code, 200)
        sql, params = self.statements('LIMIT %s OFFSET %s')[-1]
        self.assertIn('r.decided_by = %s', sql)
        self.assertIn('ORDER BY r.decided_at DESC, name', sql)
        self.assertEqual(params[:2], ['white', 'auto-external'])


class AutoApproveRunsTest(ArtistCurationTestCase):
    rules = (
        (
            'FROM rules_artist_evidence_runs',
            None,
            [
                {
                    'id': 3,
                    'started_at': '2026-09-27 04:00:00',
                    'finished_at': '2026-09-27 04:20:00',
                    'dry_run': 1,
                    'new_names': 30,
                    'backlog_names': 300,
                    'approved': 70,
                    'applied': 0,
                    'unresolved': 250,
                    'skipped': 10,
                    'incomplete': 0,
                    'requests': 900,
                    'failed_requests': 2,
                    'stopped_early': 0,
                },
            ],
        ),
        (
            'FROM rules_artist_evidence e',
            None,
            [{'name': 'Angerfist', 'rule': 'two-titles-one-act', 'run_id': 3, 'applied_at': None, 'state': None}],
        ),
    )

    def test_the_ledger_and_its_approvals_are_listed(self):
        response = self.client.get('/api/rules/artists/auto-approve/runs', headers=self.headers)
        self.assertEqual(response.status_code, 200)
        body = response.json()
        self.assertIs(body['runs'][0]['dry_run'], True)
        self.assertIs(body['runs'][0]['stopped_early'], False)
        self.assertEqual(body['approvals'][0]['name'], 'Angerfist')
        _sql, params = self.statements('FROM rules_artist_evidence e')[-1]
        self.assertEqual(params[0], 3, 'approvals from the listed rounds only')


class RecordApprovalsTest(ArtistCurationTestCase):
    def test_it_writes_what_decide_writes_for_an_approval(self):
        artist_curation.record_approvals(self.cursor, ['Angerfist', 'Ran-D'], 'auto-external')
        decisions = self.statements('INSERT INTO rules_artists')
        self.assertEqual([params[:2] for _sql, params in decisions], [('Angerfist', 'white'), ('Ran-D', 'white')])
        self.assertEqual({params[3] for _sql, params in decisions}, {'auto-external'})
        self.assertFalse(self.statements('INSERT INTO rules_ignored_artists'))

    def test_refresh_reloads_both_tagger_snapshots(self):
        artist_curation.refresh_artist_trust()
        self.assertEqual(self.reloaded_helpers(), ['rules_ignored_artists', 'library_artists'])
