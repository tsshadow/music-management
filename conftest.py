# tools/test_fetcher_trace.py is a hand-run diagnostic script, not a test module: it
# talks to the real database at import time and contains no test functions. Its name
# matches pytest's discovery pattern, so it has to be excluded explicitly.
collect_ignore = ['tools/test_fetcher_trace.py']
