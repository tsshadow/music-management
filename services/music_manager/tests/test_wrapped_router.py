"""The /api/wrapped endpoints: who may read which tab, period errors, the 503 path and refresh."""

import time
from unittest.mock import MagicMock

import pytest

pytestmark = pytest.mark.mock_base('DatabaseConnector')

from fastapi import FastAPI  # noqa: E402
from fastapi.testclient import TestClient  # noqa: E402

from services.music_manager.routers import users, wrapped  # noqa: E402
from services.music_manager.tests.scripted_cursor import ScriptedCursor  # noqa: E402

app = FastAPI()
app.include_router(wrapped.router, prefix='/api/wrapped')

SYSTEM = {'status': 'ok', 'type': 'system'}


def user(name='teun', permissions=()):
    return {'status': 'ok', 'type': 'user', 'user': {'username': name, 'permissions': list(permissions)}}


@pytest.fixture
def client(monkeypatch):
    monkeypatch.setattr(wrapped, 'server_zone_name', lambda: 'Europe/Amsterdam')
    yield TestClient(app)
    app.dependency_overrides.clear()


@pytest.fixture
def computed(monkeypatch):
    calls = []

    def fake(_connect, kind, username, period, zone, _now=None):
        calls.append((kind, username, period.key, zone.key))
        return {'scope': kind, 'cards': []}

    monkeypatch.setattr(wrapped.snapshots, 'get_or_compute', fake)
    return calls


def as_(auth):
    app.dependency_overrides[wrapped.verify_api_key] = lambda: auth


class UserTabTest:
    def test_a_user_key_reads_its_own_tab_in_its_zone(self, client, computed):
        as_(user())
        response = client.get('/api/wrapped/user?year=2026&tz=Europe/Amsterdam')
        assert response.status_code == 200
        assert response.headers['cache-control'] == 'private, max-age=300'
        assert computed == [('user', 'teun', '2026', 'Europe/Amsterdam')]

    def test_naming_another_account_is_forbidden(self, client, computed):
        as_(user())
        assert client.get('/api/wrapped/user?year=2026&username=other').status_code == 403
        assert client.get('/api/wrapped/user?year=2026&username=TEUN').status_code == 200
        assert [c[1] for c in computed] == ['teun']

    def test_the_system_key_must_name_an_account(self, client, computed):
        as_(SYSTEM)
        assert client.get('/api/wrapped/user?year=2026').status_code == 400
        assert client.get('/api/wrapped/user?year=2026&username=teun').status_code == 200
        assert len(computed) == 1

    @pytest.mark.parametrize(
        'query',
        [
            'year=2026&from=2026-01-01&to=2026-02-01',
            '',
            'from=2026-03-01&to=2026-02-01',
            'from=2020-01-01&to=2025-01-01',
            'year=2026&tz=Mars/Olympus',
        ],
    )
    def test_bad_periods_and_zones_are_400(self, client, computed, query):
        as_(user())
        assert client.get(f'/api/wrapped/user?{query}').status_code == 400
        assert computed == []

    def test_a_slow_computation_answers_503_with_retry_after(self, client, monkeypatch):
        monkeypatch.setattr(wrapped, 'COMPUTE_BUDGET_SECS', 0.05)
        monkeypatch.setattr(wrapped.snapshots, 'get_or_compute', lambda *a, **k: time.sleep(0.3) or {})
        as_(user())
        response = client.get('/api/wrapped/user?year=2026')
        assert response.status_code == 503
        assert response.headers['retry-after'] == '20'


class LibraryTabTest:
    def test_the_library_tab_uses_the_server_zone_and_no_account(self, client, computed):
        as_(user())
        assert client.get('/api/wrapped/library?from=2026-03-01&to=2026-06-30').status_code == 200
        assert computed == [('library', None, '2026-03-01_2026-06-30', 'Europe/Amsterdam')]


class PeriodsTest:
    def test_years_with_the_readers_own_count(self, client, monkeypatch):
        cursor = ScriptedCursor([('SELECT y, SUM(n) AS listens', None, [{'y': 2026, 'listens': 10, 'own_listens': 4}])])
        conn = MagicMock()
        conn.cursor.return_value = cursor
        monkeypatch.setattr(wrapped, 'get_db_connection', lambda: conn)
        as_(user())
        body = client.get('/api/wrapped/periods?tz=Europe/Amsterdam').json()
        assert body['years'] == [{'year': 2026, 'listens': 10, 'own_listens': 4}]
        assert body['server_tz'] == 'Europe/Amsterdam'
        ((_sql, params),) = cursor.statements_matching('SELECT y')
        assert params == ('teun', 'teun')

    def test_a_bad_zone_is_400(self, client):
        as_(user())
        assert client.get('/api/wrapped/periods?tz=nowhere').status_code == 400


class RefreshTest:
    def test_needs_the_permission(self, client, monkeypatch):
        monkeypatch.setattr(users, 'verify_api_key', lambda _key: user())
        response = client.post(
            '/api/wrapped/refresh', json={'scope': 'library', 'year': 2026}, headers={'x-api-key': 'k'}
        )
        assert response.status_code == 403

    def test_drops_and_queues_the_tabs(self, client, monkeypatch, computed):
        monkeypatch.setattr(users, 'verify_api_key', lambda _key: user(permissions=['wrapped.refresh']))
        cursor = ScriptedCursor(
            [
                (
                    'SELECT scope, username, period_key, tz',
                    None,
                    [{'scope': 'user', 'username': 'teun', 'period_key': '2026', 'tz': 'UTC'}],
                )
            ]
        )
        conn = MagicMock()
        conn.cursor.return_value = cursor
        monkeypatch.setattr(wrapped, 'get_db_connection', lambda: conn)
        response = client.post(
            '/api/wrapped/refresh', json={'scope': 'user', 'year': 2026, 'username': 'Teun'}, headers={'x-api-key': 'k'}
        )
        assert response.status_code == 202
        assert response.json() == {'queued': 1}
        ((_sql, params),) = cursor.statements_matching('SELECT scope')
        assert params == ('user', '2026', 'teun')
        deadline = time.time() + 2
        while not computed and time.time() < deadline:
            time.sleep(0.01)
        assert computed == [('user', 'teun', '2026', 'UTC')]

    def test_a_library_refresh_without_stored_rows_still_computes(self, client, monkeypatch, computed):
        monkeypatch.setattr(users, 'verify_api_key', lambda _key: SYSTEM)
        conn = MagicMock()
        conn.cursor.return_value = ScriptedCursor()
        monkeypatch.setattr(wrapped, 'get_db_connection', lambda: conn)
        assert client.post('/api/wrapped/refresh', json={'scope': 'library', 'year': 2026}).json() == {'queued': 1}
        deadline = time.time() + 2
        while not computed and time.time() < deadline:
            time.sleep(0.01)
        assert computed == [('library', None, '2026', 'Europe/Amsterdam')]

    @pytest.mark.parametrize(
        'body', [{'scope': 'x', 'year': 2026}, {'scope': 'user'}, {'scope': 'user', 'from': 'nope', 'to': '2026-01-01'}]
    )
    def test_bad_bodies_are_400(self, client, monkeypatch, body):
        monkeypatch.setattr(users, 'verify_api_key', lambda _key: SYSTEM)
        assert client.post('/api/wrapped/refresh', json=body).status_code == 400


def test_an_invalid_server_zone_falls_back(monkeypatch):
    class Store:
        def get(self, _key):
            return 'Not/AZone'

    monkeypatch.setattr(wrapped, 'ConfigStore', Store)
    assert wrapped.server_zone_name() == 'Europe/Amsterdam'
