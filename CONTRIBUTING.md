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
./scripts/lint.sh                       # ruff + pylint (threshold 9.5) + docstrings on strict modules
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

**Formatting is opt-in.** `./scripts/format.sh <path>` runs `ruff format` on a
directory you name. It is deliberately not in CI: a tree-wide reformat would
rewrite almost every file and conflict with every open branch.

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
