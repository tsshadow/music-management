# Contributing

This is a monorepo: the Python backend services, the C++ `music-management-server`,
the Svelte `frontend` and the Android `muma-mobile` app all live under `services/`
with one shared history. A change spanning several of them is one commit, not
several. See [AGENTS.md](AGENTS.md) for how the pieces fit together.

## Setup

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt -r requirements-dev.txt
./scripts/install-hooks.sh          # points core.hooksPath at scripts/hooks/
cp .env.example .env                # then fill in the values
```

`scripts/install-hooks.sh` uses `core.hooksPath`, so a hook change arrives with
a `git pull` rather than needing everyone to re-run it.

## Before you push

The pre-commit hook runs the first two of these. Everything here is also a CI
job, and the hook is a thin wrapper around the same scripts on purpose -- the
two can never drift apart.

```bash
./scripts/lint.sh                       # ruff + pylint (threshold 9.77) + docstrings on strict modules
./scripts/test/music-management-unit.sh # unit tests + coverage gate (84%, source only)
./scripts/typecheck.sh                  # mypy over the strict module list
./scripts/typecheck.sh --all            # mypy over the whole tree (CI: allowed to fail, for now)
./scripts/test/db-integration.sh        # endpoints + schema drift against MariaDB 13.0 (needs Docker)
./scripts/test/frontend-unit.sh         # lint + svelte-check + vitest
```

`SKIP_HOOK_TESTS=1 git commit` runs only the linter, for a docs-only change.

## The rules that are not obvious

**CI is never the place a script runs for the first time.** Run it locally, then
add it to `.gitlab-ci.yml`. Every job in there is a one-line call to a script
under `scripts/`, so the two behave identically.

**The ratchets only go up.** `FAIL_UNDER` in `scripts/lint.sh` and `COVERAGE_MIN`
in `scripts/test/music-management-unit.sh` are floors, not targets. Raise them
when the numbers climb; never lower one to make a red build green. Coverage is
measured on source only: the test files under `services/` are omitted
(`[tool.coverage.run]` in `pyproject.toml`), so a new test file cannot raise the
figure by being executed itself.

**Stubs are opt-in, per test module.** `services/tests/mock_base.py` can stand in for
`mutagen`, `yt_dlp`, `pymysql`, `dbutils`, `config_store`, `Cache`, `DatabaseConnector` and a few
more (the keys of `STUB_BUILDERS`), but only for a module that asks:

```python
import pytest

pytestmark = pytest.mark.mock_base('mutagen', 'yt_dlp', 'Cache')
```

List only what the module relies on. The marker must be module-level with literal names:
`services/tests/mock_base_plugin.py` reads it from the source before the module is imported
(the stubs have to be there while its imports run), and rejects it on a class or test. The
stubs exist while that module is imported and while its tests run; afterwards they, and every
project module imported under them, leave `sys.modules`, so the next module gets the real
libraries. Modules asking for the same set share one set of stub objects, so reset what you
change (`reset_database_helpers()` for the `Cache` helpers). To stub something just for one
test, use `patch.dict(sys.modules, {...})`, never a bare assignment --
`tests/ci/test_mock_base_isolation.py` fails when a stub outlives collection (bug report 085).

**A loop test ends the loop with a stop event, never with a patched `time.sleep`.**
`time.sleep` is one function for the whole process: a finite `side_effect` list on it is also
consumed by any other thread that sleeps during the test, and the test dies on `StopIteration`.
`thread_registry.run_forever` and the loops built on it take a `stop` event and never call
`time.sleep`; hand them `services.tests.stop_after.StopAfter(n)`, which ends the loop after
exactly `n` rounds without waiting and records the delays it was asked to wait. The process-wide
event service writes to memory in every test (`services/tests/in_memory_events_plugin.py`), so a
log line never leaves a writer thread retrying against a database (bug report 099).

**Mocked tests are not enough for SQL.** Everything under `services/` mocks the
database cursor, which proves the right query string was produced, not that
MariaDB accepts it. A new endpoint that reads from the database belongs in
`tests/integration/test_router_sql.py` as well.

**A schema change needs two edits that agree.** The `CREATE TABLE` in
`services/common/db_init.py` (or the router's `init_db`), and a `migrate_*.sql` in
the repository root (which `scripts/deploy.sh` applies on every deploy, so it must
be re-runnable). `tests/integration/test_schema_drift.py` builds the schema both
ways from an empty database and fails on any column or index that differs, so give
an index in the CREATE the name the migration gives it. The expected-table set is
read from the `CREATE TABLE` statements, not kept by hand. `CREATE TABLE IF NOT
EXISTS` never alters an existing table -- that is how two columns the code
selected went missing until the integration suite caught them.

**A write of more than one statement goes through `transaction(conn)`.** The pool
in `services/music_manager/database.py` runs autocommit, so a DELETE followed by
the INSERTs that replace it is two commits, and a `conn.commit()` afterwards does
not change that. Wrap the statements in `with transaction(conn), conn.cursor() as
cursor:` on one connection; `transaction_log` in
`services/music_manager/tests/scripted_cursor.py` asserts the BEGIN/COMMIT order in
a unit test ([design](docs/designs/db-transactions/technical.md)).

**Run the integration suite on 10.6 when you touch a TIMESTAMP column.**
`MARIADB_VERSION=10.6 ./scripts/test/db-integration.sh` runs the server
production's oldest tables were created on, which is the only one that reproduces
an implicit `ON UPDATE CURRENT_TIMESTAMP` (bug report 039). The default is 13.0,
what production runs now.

**Type checking is per module.** `pyproject.toml` holds a loose floor for the
whole tree plus a list of strictly-checked modules. Adding to that list is
welcome; removing from it needs a reason in the commit message. A module on the
list also has to document every public function and class -- `scripts/lint.sh`
fails it otherwise -- so document a module before adding it.

**Formatting is checked.** `./scripts/format.sh` runs `ruff format` over
`services/`, `tools/` and `tests/`, or over the paths you name. The
`backend:format` job and the pre-commit hook run `./scripts/format.sh --check`
and fail on an unformatted file. The whole-tree reformat is listed in
`.git-blame-ignore-revs`.

## Branches and releases

`feature/*` → `develop` → `release/x.y.z` → `master`. The release branch is where
stabilisation and the production deploy happen; `master` is the tagged record.
[docs/release-management.md](docs/release-management.md) has the full policy,
including what the `release:check-secrets` job guarantees.

## Commit messages

Conventional Commits (`feat:`, `fix:`, `chore:`, `test:`, `docs:`, `refactor:`),
present tense. The body should say why, not what -- the diff already says what.
If a change works around something surprising, the reason belongs in a code
comment as well, where the next person will actually hit it.

## Reporting a bug

Bugs that reached production get a numbered write-up in `docs/bug-reports/`
covering the symptom, the cause and what now prevents a recurrence. That
directory is the most useful documentation in this repository; keep it fed.

## Open work

Anything decided but not done, or done but not verified, becomes a
[GitLab issue](https://gitlab.example.com/muma/music-management/-/issues)
right away (`glab issue create`), with one kind label (`needs-person`,
`decision`, `verify`, `code`, `deferred`) and one area label (`area-backend`,
`area-frontend`, `area-mobile`, `area-lms`, `area-infra`, `area-data`), and a
link to the bug report or design that holds the detail. A `verify` issue states
the exact check. A merge request that finishes an issue says `Closes #N` in its
description. `docs/open-work.md` is only a pointer to the issues now; do not add
lines to it. AGENTS.md rule 14 is the rule.
