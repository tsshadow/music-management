import os

import pytest

# The system API key has no literal fallback in the source any more (see
# services/music_manager/api_key.py), so this suite has to supply one. It runs the app
# in-process, so one value covers both sides. 'test-api-key' is what
# docker/compose.test.yml starts the containerised music-manager with and what
# tests/contracts/ defaults to, so every suite agrees on the same key.
#
# Module level rather than pytest_configure: this has to land before main.py is
# imported. setdefault, plus load_dotenv's own refusal to override, keeps the run
# independent of whatever API_KEY a developer's .env deploys with.
os.environ.setdefault('API_KEY', 'test-api-key')


def pytest_configure(config):
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
