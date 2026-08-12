# tools/test_fetcher_trace.py is a hand-run diagnostic script, not a test module: it
# talks to the real database at import time and contains no test functions. Its name
# matches pytest's discovery pattern, so it has to be excluded explicitly.
collect_ignore = ['tools/test_fetcher_trace.py']

# Deliberately no API_KEY default here. tests/contracts/ drives a *containerised*
# music-manager over HTTP and reads os.getenv('API_KEY', 'test-api-key') to match the
# value docker/compose.test.yml starts that container with; a default set this high up
# is inherited by the runner process and silently overrides it, which makes every
# contract request 401. The suites that run the app in-process set it themselves --
# see services/conftest.py and tests/integration/conftest.py.
