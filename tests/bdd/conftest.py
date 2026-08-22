"""Fixtures and shared steps for the Gherkin walk of the server chain.

Ports rather than hostnames because the stack publishes on the host and both are
picked free at runtime; scripts/test/core-e2e.sh is what exports them. Skipping
rather than failing when they are unset is deliberate: a bare `pytest tests/bdd`
with no stack up should say so, not report a broken chain.

Steps live here when more than one feature uses them. pytest-bdd resolves step
definitions from conftest.py as well as from the module next to the feature, so
this is where a Given shared by two features belongs -- copying it into both is
how the two slowly stop meaning the same thing.
"""
from __future__ import annotations

import os

import pytest
import requests
from pytest_bdd import given

TIMEOUT = 10


def _base(port_var: str) -> str:
    port = os.getenv(port_var)
    if not port:
        pytest.skip(f'{port_var} is not set; start the stack with scripts/test/core-e2e.sh')
    return f'http://127.0.0.1:{port}'


@pytest.fixture(scope='session')
def manager() -> str:
    return _base('MUMA_TEST_PORT_MANAGER')


@pytest.fixture(scope='session')
def lms() -> str:
    return _base('MUMA_TEST_PORT_LMS')


@pytest.fixture(scope='session')
def api_key() -> str:
    return os.getenv('API_KEY') or 'test-api-key'


@pytest.fixture(scope='session')
def subsonic_auth() -> dict:
    """Credentials for LMS, which has no users of its own.

    music-manager owns the accounts and pushes them across; the one used here is
    created by e2e_stack_scan_lms before pytest starts. Subsonic reports a bad
    password inside a 200, so a wrong value here does not fail loudly -- it
    quietly turns every LMS assertion into a check that the process is listening.
    """
    return {
        'u': os.getenv('MUMA_TEST_LMS_USER') or 'e2e-admin',
        'p': os.getenv('MUMA_TEST_LMS_PASSWORD') or 'e2e-password',
        'v': '1.16.1',
        'c': 'e2e-test',
        'f': 'json',
    }


@pytest.fixture
def context() -> dict:
    """What one step hands to the next.

    Gherkin steps are functions with no return value to pass around, so the
    thing under test has to live somewhere both can reach. Function-scoped, so a
    second scenario never inherits the first one's track.
    """
    return {}


def stats(manager: str, api_key: str) -> dict:
    """music-manager's own counters, which is the only way back to what it kept.

    Neither listen table has an endpoint that serves rows: `scrobble_listens` and
    `scrobble_unmatched_listens` are written by the scrobble endpoint and read
    here and by the rematcher, and by nothing else. So a feature can assert that
    a listen was stored, and cannot assert which one -- the counters are the
    whole surface.
    """
    response = requests.get(f'{manager}/api/stats/', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, response.text
    return response.json()


@given('the test stack is running')
def _stack_is_running(manager, api_key):
    """Shared by every feature: nothing below means anything without it.

    It asserts rather than does nothing, because a Given that quietly passes lets
    a whole scenario run green against a stack that never came up.
    """
    response = requests.get(f'{manager}/health', headers={'x-api-key': api_key}, timeout=TIMEOUT)
    assert response.status_code == 200, (
        f'music-manager is not answering on {manager}: {response.status_code} {response.text}'
    )
