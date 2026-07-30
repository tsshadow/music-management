# title: `genre-processor` and `muma-soundcloud-fetcher` containers crash on start with `ModuleNotFoundError`

# status: fixed

# reported problem
Checking `docker ps -a` on production (192.0.2.27) showed both the `genre-processor` and
`muma-soundcloud-fetcher` containers in an `Exited (1)` state, while every other container in the
stack was `Up`/healthy. `docker logs` for both showed a Python traceback ending in
`ModuleNotFoundError`:
- `genre-processor` (`tools/process_genres.py --run --interactive`):
  `ModuleNotFoundError: No module named 'services.common.api'`
- `muma-soundcloud-fetcher` (`tools/soundcloud_fetcher.py`):
  `ModuleNotFoundError: No module named 'services.common.settings'`

# Possible reason
An earlier refactor (commit `cb345cf79`, "Final cleanup and centralization of API and
configuration") removed `services/common/settings.py` (replaced by
`services.common.config_store.ConfigStore`) and moved `services/common/api/db_init.py` to
`services/common/db_init.py`. All call sites under `services/` and `tools/fix_imports.py` were
updated in that same commit, but `tools/soundcloud_fetcher.py` (top-level
`from services.common.settings import Settings`) and `tools/process_genres.py` (inline
`from services.common.api.db_init import ensure_tables_exist` used in the non-dry-run path) were
missed, since the `tools/` scripts are not covered by the regular `services/` unit test suite
(`scripts/test/music-management-unit.sh`) and therefore the stale imports were never exercised by
CI — the images built and shipped fine, only failing at container runtime.

# solution
- `tools/soundcloud_fetcher.py`: changed `from services.common.settings import Settings` to
  `from services.common.config_store import ConfigStore as Settings`, matching the pattern already
  used by `services/downloader/downloader_service.py`.
- `tools/process_genres.py`: applied the same `Settings` fix to its (already `try`/`except
  ImportError`-guarded) top-level import, and fixed the unguarded
  `from services.common.api.db_init import ensure_tables_exist` to
  `from services.common.db_init import ensure_tables_exist`.
- Added `tools/test_tools_imports.py`, which imports both scripts and exercises
  `process_genres(dry_run=False)` (safe without a live DB — `ensure_tables_exist()` and the
  table helpers degrade gracefully to a logged warning on connection failure) so a future
  `services.common` refactor that misses these two scripts fails CI instead of only surfacing in
  production. Wired it into `scripts/test/music-management-unit.sh`'s `TEST_TARGETS`.
