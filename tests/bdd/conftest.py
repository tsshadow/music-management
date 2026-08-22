"""Fixtures for the Gherkin walk of the scan-to-listen chain.

Ports rather than hostnames because the stack publishes on the host and both are
picked free at runtime; scripts/test/core-e2e.sh is what exports them. Skipping
rather than failing when they are unset is deliberate: a bare `pytest tests/bdd`
with no stack up should say so, not report a broken chain.
"""
from __future__ import annotations

import os

import pytest


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
