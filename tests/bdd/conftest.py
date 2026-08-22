"""Fixtures for the Gherkin walk of the scan-to-listen chain.

Deliberately the same shape as the ones in tests/e2e/: the pilot is a comparison
of two ways of *describing* one chain, so the way the stack is reached has to be
identical for the comparison to say anything.
"""
from __future__ import annotations

import os

import pytest


def _base(port_var: str) -> str:
    port = os.getenv(port_var)
    if not port:
        pytest.skip(f'{port_var} is not set; start the stack with scripts/test/e2e-gherkin.sh')
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


@pytest.fixture
def context() -> dict:
    """What one step hands to the next.

    Gherkin steps are functions with no return value to pass around, so the
    thing under test has to live somewhere both can reach. Function-scoped, so a
    second scenario never inherits the first one's track.
    """
    return {}
