# mock_base stubs replaced real modules for the whole test session

# status: fixed

# reported problem

`services/tests/mock_base.py`, loaded by `services/conftest.py`'s `pytest_configure`, replaced
`mutagen`, `pymysql`, `yt_dlp`, `patoolib`, `librosa`, `numpy`, `sqlalchemy`, `dotenv`,
`config_store`, `ProcessedFilesHelper`, `DatabaseConnector`, `Cache` and more in `sys.modules`
the moment it was imported, for every test in the same session -- including `tools/`, `tests/ci/`
and `tests/unit/`, which only happened to be collected in the same run. Seen consequences:

- a test that needed the real module got a stub, so several tests loaded the real source file by
  path under a throwaway name just to get past it, and `tests/unit/` existed only to run real
  mutagen and yt-dlp in child interpreters;
- a guard test could not build a real `ConfigStore` when it ran alongside the router tests;
- `MagicMock` values leaked into real output: bug report 082's ntfy pushes read
  `Downloads failed: <MagicMock name='mock.ConfigStore().get()' ...>`, and every local unit run
  still printed 19 `NtfySink: push naar <MagicMock ...> mislukt` lines.

# Possible reason

The stubs were installed as an import side effect, once, and never removed. On top of that, 52
router test modules ran `sys.modules.setdefault(name, MagicMock())` for `pymysql`, `dbutils`,
`mutagen` and `markdown` at import time; under the session-wide stubs that was a no-op, but in a
session where the stubs were absent it would have installed bare MagicMocks for everything
collected afterwards. Three connector tests assigned `sys.modules['pymysql'] = MagicMock()` and
did not (or only sometimes) put the old value back.

# solution

The stubs are opt-in per test module. A module declares what it relies on:

```python
pytestmark = pytest.mark.mock_base('mutagen', 'yt_dlp', 'Cache')
```

`services/tests/mock_base_plugin.py` (registered from the root `conftest.py`) reads that marker
from the file's source with `ast` before import, installs exactly those stubs while the module is
imported and while its tests run, and restores `sys.modules` afterwards. Every project module
imported under the stubs is lifted out again with them, so a later module that asked for nothing
imports the real code; modules that ask for the same set share one "world". A marker on a class
or function is rejected at collection, since it could not take effect. `mock_base.py` itself only
builds stubs on request now (`STUB_BUILDERS`), and `setup_mocks()` is gone.

Inventory (unit suite, `./scripts/test/music-management-unit.sh`), taken by running with every
stub for every module, with none, and with each stub left out once:

- `Cache`: 33 modules (tagger song types, downloader and importer flows, four curation routers).
- `mutagen`: 15 modules that assert on tags written through the stub containers, plus 43 of the
  router modules below.
- `yt_dlp`: 19 downloader modules fail against the real yt-dlp. 13 more import it through the
  code under test and pass against the real one, but a developer's interpreter without yt-dlp
  (the pre-commit hook runs natively) cannot import them at all, so they declare it too. (Leaving
  it out while keeping the mutagen stub breaks all of them: a real yt-dlp imports
  `mutagen.flac.Picture`, which the stub lacks.)
- `config_store`: 5 downloader modules.
- `DatabaseConnector`: 42 router modules (importing `main` builds a `Tagger`, whose
  `ProcessedFilesHelper.create_table()` would connect), and 4 of those need `Cache` as well.
- `pymysql`, `dbutils` (52 modules), `markdown` and `mutagen` (43 of them): what each module's
  `setdefault` loop asked for; the loop is replaced by those names in the marker, so they keep
  exactly the stubs they used before. A follow-up pruned them name by name (each module alone
  and within the whole `services/music_manager/tests` run): none of the router modules needs any
  of the four against the real libraries. The one test that failed without `dbutils`,
  `test_radio`'s permission check, patched a `verify_api_key` the route never uses and only
  passed because the stubbed pool answered the real lookup; it overrides the dependency now.
- ml-analyzer (`./scripts/test/ml-analyzer-unit.sh`): `librosa`, `sqlalchemy`, `pandas`, `tqdm`,
  `dotenv`.
- `patoolib`: the 2 importer modules that import the extractor, for the same reason as the 13
  yt-dlp ones -- they pass against the real patool, but it must not have to be installed.
- Not needed by any collected test: `numpy`, `joblib`, `sklearn`, `ProcessedFilesHelper`. They
  stay available to the marker.

104 of the 270 unit test modules carry a marker (plus the four ml-analyzer ones); the rest run
against the real modules. The three connector tests use `patch.dict(sys.modules, ...)`, and `tests/unit/test_downloader_real_ytdlp.py`
builds its child's stubs explicitly. `tests/ci/test_mock_base_isolation.py` fails if any
stub is in `sys.modules` after collection, including in a fresh interpreter that has just
collected two heavily stubbed modules. The unit run went from 240 s to 160 s and prints no
MagicMock push attempts; coverage is unchanged (88.8%).
