import os

# tools/test_fetcher_trace.py is a hand-run diagnostic script, not a test module: it
# talks to the real database at import time and contains no test functions. Its name
# matches pytest's discovery pattern, so it has to be excluded explicitly.
collect_ignore = ['tools/test_fetcher_trace.py']

# The system API key has no literal fallback in the source any more (see
# services/music_manager/api_key.py), so the suites have to supply one. This is the
# root conftest precisely because it is the only one on the path to *both* trees:
# services/conftest.py is not loaded for tests/integration/, which is the whole
# reason that suite lives outside services/.
#
# setdefault, plus load_dotenv's own refusal to override, keeps this independent of
# whatever API_KEY a developer's .env deploys with. It runs at import, before any
# test module -- and therefore before main.py -- is imported.
os.environ.setdefault('API_KEY', 'test-system-api-key')
