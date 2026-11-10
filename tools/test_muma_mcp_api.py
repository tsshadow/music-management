"""The production HTTP client, tools/muma_mcp/api.py. Nothing here touches a network."""

from __future__ import annotations

from unittest.mock import patch

import pytest
import requests

from tools.muma_mcp import api
from tools.muma_mcp.config import Config

CONFIG = Config(
    prod_url='http://192.0.2.27:8000',
    api_key='the-system-key',
    db_host='192.0.2.27',
    db_port=3306,
    db_user='muma-readonly',
    db_pass='the-db-password',
    db_name='music-management',
)


class FakeResponse:
    def __init__(self, status_code=200, payload=None, text=''):
        self.status_code = status_code
        self._payload = payload
        self.text = text
        self.ok = 200 <= status_code < 300

    def json(self):
        if self._payload is None:
            raise ValueError('no json')
        return self._payload


def test_health_sends_the_api_key():
    """Without a key /health answers the status alone (issue #218); the version needs the key."""
    with patch('tools.muma_mcp.api.requests.get', return_value=FakeResponse(payload={'version': '0.40.0'})) as get:
        assert api.health(CONFIG) == {'version': '0.40.0'}

    assert get.call_args.kwargs['headers'] == {'X-API-Key': 'the-system-key'}
    assert get.call_args.args[0] == 'http://192.0.2.27:8000/health'


def test_containers_sends_the_api_key():
    with patch('tools.muma_mcp.api.requests.get', return_value=FakeResponse(payload=[])) as get:
        api.containers(CONFIG)

    assert get.call_args.kwargs['headers'] == {'X-API-Key': 'the-system-key'}
    assert get.call_args.args[0] == 'http://192.0.2.27:8000/api/system/containers'


def test_logs_uses_the_api_prefix_without_management():
    """main.py mounts the management router at /api; /api/management/... is a 404."""
    with patch('tools.muma_mcp.api.requests.get', return_value=FakeResponse(payload={'logs': ''})) as get:
        api.logs(CONFIG, 'muma-manager')

    assert get.call_args.args[0] == 'http://192.0.2.27:8000/api/system/logs/muma-manager'


def test_logs_are_redacted_with_the_configured_secrets():
    payload = {'logs': f'connecting with {CONFIG.db_pass} and key {CONFIG.api_key}'}
    with patch('tools.muma_mcp.api.requests.get', return_value=FakeResponse(payload=payload)):
        result = api.logs(CONFIG, 'muma-manager')

    assert CONFIG.db_pass not in result
    assert CONFIG.api_key not in result


@pytest.mark.parametrize(('requested', 'expected'), [(0, 1), (-5, 1), (50, 50), (99999, 2000)])
def test_tail_is_clamped(requested, expected):
    with patch('tools.muma_mcp.api.requests.get', return_value=FakeResponse(payload={'logs': ''})) as get:
        api.logs(CONFIG, 'muma-manager', tail=requested)

    assert get.call_args.kwargs['params'] == {'tail': expected}


def test_unreachable_host_says_so_without_blaming_production():
    """In a sandboxed session the LAN is unreachable; that is not an outage."""
    with (
        patch('tools.muma_mcp.api.requests.get', side_effect=requests.ConnectTimeout('timeout')),
        pytest.raises(api.ProdApiError, match='gesandboxte'),
    ):
        api.health(CONFIG)


@pytest.mark.parametrize('status', [401, 403])
def test_rejected_key_is_reported_as_such(status):
    with (
        patch('tools.muma_mcp.api.requests.get', return_value=FakeResponse(status_code=status)),
        pytest.raises(api.ProdApiError, match='API-sleutel'),
    ):
        api.containers(CONFIG)


def test_server_error_is_reported_with_its_status():
    with (
        patch('tools.muma_mcp.api.requests.get', return_value=FakeResponse(status_code=500)),
        pytest.raises(api.ProdApiError, match='500'),
    ):
        api.containers(CONFIG)


def test_non_json_answer_quotes_what_came_back():
    """The LMS proxy gate answers a burst with plain text, naming the wrong component."""
    response = FakeResponse(payload=None, text='Too many requests')
    with (
        patch('tools.muma_mcp.api.requests.get', return_value=response),
        pytest.raises(api.ProdApiError, match='Too many requests'),
    ):
        api.health(CONFIG)
