"""The channel link proposals: search, confirm, reject, unlink. See docs/designs/channel-links."""

import unittest
from unittest.mock import MagicMock, patch

import pytest

pytestmark = pytest.mark.mock_base('mutagen', 'markdown', 'pymysql', 'dbutils', 'DatabaseConnector')


import services.music_manager.routers.users as users_router
from services.music_manager.api_key import resolve_system_api_key

users_router.run_lms_db_sync = lambda: None

from fastapi.testclient import TestClient

from services.music_manager.main import app
from services.music_manager.routers import channel_links as router_module
from services.music_manager.tests.scripted_cursor import normalize

API_KEY = resolve_system_api_key()


class FakeDatabase:
    """Just enough of the five input tables and channel_link_proposals to run the router's SQL.

    Statements are recognised by the router's own query constants, so a changed query
    string fails here rather than silently matching nothing.
    """

    def __init__(self, channels=(), labels=(), approved=(), aliases=(), redirects=(), proposals=(), targets=None):
        self.channels = {c['id']: dict(c) for c in channels}
        self.labels = list(labels)
        self.approved = list(approved)
        self.aliases = list(aliases)
        self.redirects = list(redirects)
        self.proposals = {}
        for row in proposals:
            self.proposals[row['id']] = {'status': 'new', 'decided_by': None, **row}
        # (kind, id) pairs the library still has; defaults to every label and approved artist.
        self.targets = (
            targets
            if targets is not None
            else ({('label', i) for i, _ in labels} | {('artist', i) for i, _ in approved})
        )
        self.executed = []
        self.rowcount = 0
        self._result = []

    # -- cursor protocol
    def __enter__(self):
        return self

    def __exit__(self, *_exc):
        return False

    def fetchall(self):
        return list(self._result)

    def fetchone(self):
        return self._result[0] if self._result else None

    def execute(self, sql, params=()):
        statement = normalize(sql)
        self.executed.append((statement, params))
        self._result = []
        self.rowcount = 0
        if statement == normalize(router_module.CHANNELS_QUERY):
            self._result = [c for c in self.channels.values() if c['platform'] in params]
        elif statement == normalize(router_module.LABELS_QUERY):
            self._result = [{'id': i, 'name': n} for i, n in self.labels]
        elif statement == normalize(router_module.APPROVED_ARTISTS_QUERY):
            self._result = [{'id': i, 'name': n} for i, n in self.approved]
        elif statement == normalize(router_module.ALIASES_QUERY):
            self._result = [{'id': i, 'name': n, 'alias': a} for i, n, a in self.aliases]
        elif statement == normalize(router_module.REDIRECTS_QUERY):
            self._result = [{'id': i, 'name': n, 'spelling': s} for i, n, s in self.redirects]
        elif statement == normalize(router_module.RECORD_QUERY):
            self._record(*params)
        elif statement == normalize(router_module.OPEN_QUERY):
            self._result = [dict(p) for p in self.proposals.values() if p['status'] == 'new']
        elif statement.startswith('SELECT id, channel_id, kind, target_id, status FROM channel_link_proposals'):
            row = self.proposals.get(params[0])
            self._result = [dict(row)] if row else []
        elif statement.startswith('SELECT label_id AS linked') or statement.startswith('SELECT artist_id AS linked'):
            column = statement.split()[1]
            channel = self.channels.get(params[0])
            self._result = [{'linked': channel.get(column)}] if channel else []
        elif statement.startswith('SELECT id FROM library_labels') or statement.startswith(
            'SELECT id FROM library_artists'
        ):
            kind = 'label' if 'library_labels' in statement else 'artist'
            self._result = [{'id': params[0]}] if (kind, params[0]) in self.targets else []
        elif statement.startswith('SELECT id FROM channels'):
            self._result = [{'id': params[0]}] if params[0] in self.channels else []
        elif statement.startswith('UPDATE channels SET'):
            column = statement.split()[3]
            value, channel_id = (None, params[0]) if 'NULL' in statement else params
            self.channels[channel_id][column] = value
            self.rowcount = 1
        elif statement.startswith('UPDATE channel_link_proposals'):
            self._update_proposals(statement, params)
        else:
            raise AssertionError(f'unexpected statement: {statement}')

    def _record(self, channel_id, kind, target_id, target_name, source):
        for row in self.proposals.values():
            if (row['channel_id'], row['kind'], row['target_id']) == (channel_id, kind, target_id):
                if row['status'] == 'new' and (row['target_name'], row['source']) != (target_name, source):
                    row.update(target_name=target_name, source=source)
                    self.rowcount = 2
                return
        new_id = max(self.proposals, default=0) + 1
        self.proposals[new_id] = {
            'id': new_id,
            'channel_id': channel_id,
            'kind': kind,
            'target_id': target_id,
            'target_name': target_name,
            'source': source,
            'status': 'new',
            'decided_by': None,
        }
        self.rowcount = 1

    def _update_proposals(self, statement, params):
        status = statement.split("status = '")[1].split("'")[0]
        if 'WHERE id = %s AND status' in statement or statement.endswith('WHERE id = %s'):
            ids = [params[-1]]
        elif 'AND id <> %s' in statement:
            channel_id, kind, keep = params
            ids = [
                i
                for i, p in self.proposals.items()
                if (p['channel_id'], p['kind'], p['status']) == (channel_id, kind, 'new') and i != keep
            ]
        else:  # unlink: the confirmed proposal of a channel and kind
            _, channel_id, kind = params
            ids = [
                i
                for i, p in self.proposals.items()
                if (p['channel_id'], p['kind'], p['status']) == (channel_id, kind, 'confirmed')
            ]
        for i in ids:
            if "AND status = 'new'" in statement and self.proposals[i]['status'] != 'new':
                continue
            self.proposals[i]['status'] = status
            if 'decided_by' in statement:
                self.proposals[i]['decided_by'] = params[0]
        self.rowcount = len(ids)

    def writes(self):
        return [s for s, _ in self.executed if s.startswith(('INSERT', 'UPDATE'))]


class ChannelLinksTestCase(unittest.TestCase):
    def setUp(self):
        self.client = TestClient(app)
        self.headers = {'x-api-key': API_KEY}
        self.use(FakeDatabase())

    def use(self, db):
        self.db = db
        conn = MagicMock()
        conn.cursor.return_value = db
        patcher = patch.object(router_module, 'get_db_connection', return_value=conn)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.conn = conn

    def post(self, path):
        return self.client.post(f'/api/channel-links{path}', headers=self.headers)


def library():
    """Two channels: one is a label and an artist, one is ambiguous between two spellings."""
    return FakeDatabase(
        channels=[
            {'id': 1, 'platform': 'soundcloud', 'name': 'Monstercat', 'label_id': None, 'artist_id': None},
            {'id': 2, 'platform': 'youtube', 'name': 'Dimitri-K', 'label_id': None, 'artist_id': None},
            {'id': 3, 'platform': 'telegram', 'name': 'Monstercat', 'label_id': None, 'artist_id': None},
        ],
        labels=[(10, 'Monstercat')],
        approved=[(20, 'Monstercat'), (21, 'Dimitri K'), (22, 'Dimitri K.')],
    )


class RefreshTest(ChannelLinksTestCase):
    def test_the_search_files_what_holds_and_counts_the_ambiguous(self):
        self.use(library())
        body = self.post('/proposals/refresh').json()
        self.assertEqual({'created': 2, 'open': 2, 'withdrawn': 0, 'ambiguous': 1}, body)
        self.assertEqual(
            {(1, 'label', 10), (1, 'artist', 20)},
            {(p['channel_id'], p['kind'], p['target_id']) for p in self.db.proposals.values()},
        )
        self.conn.begin.assert_called()
        self.conn.commit.assert_called()

    def test_a_second_search_in_a_row_changes_nothing(self):
        self.use(library())
        self.post('/proposals/refresh')
        before = {i: dict(p) for i, p in self.db.proposals.items()}
        body = self.post('/proposals/refresh').json()
        self.assertEqual(0, body['created'])
        self.assertEqual(0, body['withdrawn'])
        self.assertEqual(before, self.db.proposals)
        self.assertFalse([s for s in self.db.writes()[-2:] if s.startswith('UPDATE')])

    def test_a_rejected_proposal_is_never_reopened(self):
        self.use(library())
        self.post('/proposals/refresh')
        label_id = next(i for i, p in self.db.proposals.items() if p['kind'] == 'label')
        self.post(f'/proposals/{label_id}/reject')
        self.post('/proposals/refresh')
        self.assertEqual('rejected', self.db.proposals[label_id]['status'])
        self.assertEqual(2, len(self.db.proposals))

    def test_an_open_proposal_that_no_longer_holds_is_withdrawn(self):
        self.use(library())
        self.post('/proposals/refresh')
        self.db.approved = [(21, 'Dimitri K')]  # Monstercat is no longer an approved artist
        body = self.post('/proposals/refresh').json()
        self.assertEqual(1, body['withdrawn'])
        artist = next(p for p in self.db.proposals.values() if p['kind'] == 'artist')
        self.assertEqual('stale', artist['status'])

    def test_searching_needs_the_rule_permission(self):
        response = self.client.post('/api/channel-links/proposals/refresh')
        self.assertIn(response.status_code, (401, 403))


def with_open_proposals(**overrides):
    db = FakeDatabase(
        channels=[{'id': 1, 'platform': 'soundcloud', 'name': 'Monstercat', 'label_id': None, 'artist_id': None}],
        labels=[(10, 'Monstercat'), (11, 'Monstercat Records')],
        proposals=[
            {'id': 5, 'channel_id': 1, 'kind': 'label', 'target_id': 10, 'target_name': 'Monstercat', 'source': 'name'},
            {
                'id': 6,
                'channel_id': 1,
                'kind': 'label',
                'target_id': 11,
                'target_name': 'Monstercat Records',
                'source': 'name',
            },
        ],
        **overrides,
    )
    return db


class ConfirmTest(ChannelLinksTestCase):
    def test_confirming_links_the_channel_and_withdraws_its_rivals(self):
        self.use(with_open_proposals())
        body = self.post('/proposals/5/confirm').json()
        self.assertEqual({'status': 'confirmed', 'channel_id': 1, 'kind': 'label', 'target_id': 10}, body)
        self.assertEqual(10, self.db.channels[1]['label_id'])
        self.assertEqual('confirmed', self.db.proposals[5]['status'])
        self.assertEqual('stale', self.db.proposals[6]['status'])
        self.conn.commit.assert_called_once()

    def test_confirming_twice_writes_nothing_the_second_time(self):
        self.use(with_open_proposals())
        self.post('/proposals/5/confirm')
        writes = len(self.db.writes())
        body = self.post('/proposals/5/confirm').json()
        self.assertEqual('confirmed', body['status'])
        self.assertEqual(writes, len(self.db.writes()))

    def test_a_deleted_target_makes_the_proposal_stale(self):
        self.use(with_open_proposals(targets={('label', 11)}))
        body = self.post('/proposals/5/confirm').json()
        self.assertEqual('stale', body['status'])
        self.assertIsNone(self.db.channels[1]['label_id'])
        self.assertEqual('stale', self.db.proposals[5]['status'])

    def test_a_channel_linked_to_another_target_is_a_conflict(self):
        db = with_open_proposals()
        db.channels[1]['label_id'] = 11
        self.use(db)
        response = self.post('/proposals/5/confirm')
        self.assertEqual(409, response.status_code)
        self.conn.rollback.assert_called_once()

    def test_a_rejected_proposal_cannot_be_confirmed(self):
        db = with_open_proposals()
        db.proposals[5]['status'] = 'rejected'
        self.use(db)
        self.assertEqual(409, self.post('/proposals/5/confirm').status_code)

    def test_an_unknown_proposal_is_a_404(self):
        self.assertEqual(404, self.post('/proposals/99/confirm').status_code)


class RejectAndUnlinkTest(ChannelLinksTestCase):
    def test_rejecting_is_idempotent(self):
        self.use(with_open_proposals())
        self.assertEqual({'status': 'rejected'}, self.post('/proposals/5/reject').json())
        writes = len(self.db.writes())
        self.assertEqual({'status': 'rejected'}, self.post('/proposals/5/reject').json())
        self.assertEqual(writes, len(self.db.writes()))

    def test_a_confirmed_proposal_is_unlinked_not_rejected(self):
        self.use(with_open_proposals())
        self.post('/proposals/5/confirm')
        self.assertEqual(409, self.post('/proposals/5/reject').status_code)

    def test_unlinking_clears_the_link_and_rejects_its_proposal(self):
        self.use(with_open_proposals())
        self.post('/proposals/5/confirm')
        response = self.client.delete('/api/channel-links/channels/1/label', headers=self.headers)
        self.assertEqual({'status': 'unlinked'}, response.json())
        self.assertIsNone(self.db.channels[1]['label_id'])
        self.assertEqual('rejected', self.db.proposals[5]['status'])

    def test_unlinking_an_unknown_kind_or_channel_is_refused(self):
        self.assertEqual(
            400, self.client.delete('/api/channel-links/channels/1/genre', headers=self.headers).status_code
        )
        self.assertEqual(
            404, self.client.delete('/api/channel-links/channels/9/label', headers=self.headers).status_code
        )


class ListTest(ChannelLinksTestCase):
    def test_the_list_filters_on_status_and_kind(self):
        cursor = MagicMock()
        cursor.fetchall.return_value = [{'id': 5}]
        conn = MagicMock()
        conn.cursor.return_value.__enter__.return_value = cursor
        with patch.object(router_module, 'get_db_connection', return_value=conn):
            response = self.client.get('/api/channel-links/proposals?kind=artist', headers=self.headers)
        self.assertEqual([{'id': 5}], response.json())
        sql, params = cursor.execute.call_args.args
        self.assertIn('p.kind = %s', sql)
        self.assertEqual(('new', 'artist', 'artist'), params)

    def test_an_unknown_status_or_kind_is_refused(self):
        self.assertEqual(
            400, self.client.get('/api/channel-links/proposals?status=maybe', headers=self.headers).status_code
        )
        self.assertEqual(
            400, self.client.get('/api/channel-links/proposals?kind=genre', headers=self.headers).status_code
        )


if __name__ == '__main__':
    unittest.main()
