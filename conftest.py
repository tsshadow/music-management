import os

# No test may ever push to the real ntfy server. services/common/config_store.py runs
# load_dotenv() at import time, so a developer's .env (which carries NOTIFY_URL) turned
# every local test run -- including pre-commit hooks -- into real phone notifications:
# on 2026-09-25 the artist-image router test pushed "Downloads failed: <MagicMock ...>"
# six times in five hours (bug report 082). load_dotenv never overrides a variable that
# is already set, so blanking it here, before any test module imports config_store,
# makes NtfySink find no URL and return. Anything that genuinely needs a URL in a test
# passes its own config object to NtfySink.
os.environ['NOTIFY_URL'] = ''

# tools/test_fetcher_trace.py is a hand-run diagnostic script, not a test module: it
# talks to the real database at import time and contains no test functions. Its name
# matches pytest's discovery pattern, so it has to be excluded explicitly.
collect_ignore = ['tools/test_fetcher_trace.py']

# `@pytest.mark.mock_base(...)`: the opt-in, per-module stubs of services/tests/mock_base.py
# (bug report 085). Registered here, at the root, so tools/ and tests/ can use it too.
#
# `services.tests.in_memory_events_plugin`: the process-wide event service writes to an
# in-memory list instead of the database, so a log line in one test never leaves the event
# writer retrying against a database while later tests run (bug report 099).
pytest_plugins = ['services.tests.mock_base_plugin', 'services.tests.in_memory_events_plugin']

# Deliberately no API_KEY default here. tests/contracts/ drives a *containerised*
# music-manager over HTTP and reads os.getenv('API_KEY', 'test-api-key') to match the
# value docker/compose.test.yml starts that container with; a default set this high up
# is inherited by the runner process and silently overrides it, which makes every
# contract request 401. The suites that run the app in-process set it themselves --
# see services/conftest.py and tests/integration/conftest.py.
