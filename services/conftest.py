import os

import pytest


def pytest_configure(config):
    # The system API key no longer has a literal fallback in the source, so the
    # suite has to supply one. setdefault (plus load_dotenv's own refusal to
    # override) means this wins over any API_KEY in a developer's .env, keeping
    # the tests independent of whatever that machine deploys with.
    os.environ.setdefault('API_KEY', 'test-system-api-key')

    from services.tests import mock_base
    mock_base.setup_mocks()


@pytest.fixture(autouse=True)
def _reset_auth_rate_limiter():
    """Give every test a clean rate-limit window.

    The authentication endpoints are rate limited per client address, and the
    TestClient always presents the same one, so without this the tests would
    start limiting each other after ten logins. Resetting afterwards as well
    keeps a test that deliberately exhausts the window from leaking into the
    next one.
    """
    try:
        from services.music_manager.rate_limit import auth_limiter
    except Exception:  # the limiter only exists once music_manager is importable
        yield
        return
    auth_limiter.reset()
    yield
    auth_limiter.reset()
