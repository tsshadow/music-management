- **Test stubs no longer leak into every other test.** `services/tests/mock_base.py` used to replace
  mutagen, pymysql, yt-dlp, `config_store`, `Cache`, `DatabaseConnector` and more in `sys.modules`
  for the whole pytest session, so a test that needed the real module got a MagicMock, and MagicMock
  values reached real output (bug report 082's ntfy pushes). A test module now asks for exactly the
  stubs it relies on with `pytestmark = pytest.mark.mock_base(...)`; they exist only while that
  module is imported and its tests run, and everything imported under them leaves `sys.modules`
  again afterwards. 104 of 270 unit test modules declare stubs, the rest run against the real
  libraries. `tests/ci/test_mock_base_isolation.py` fails if a stub survives collection. The unit
  run is faster (about 160 s instead of 240 s) and coverage is unchanged. Bug report 085; the marker
  is documented in `CONTRIBUTING.md` and `AGENTS.md`.

<!-- release notes -->

- **Internal: the test suite no longer lets its stand-in libraries leak between tests.** No change
  in the app or the server.
