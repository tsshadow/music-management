# Schema Drift Was Invisible To The Integration Suite, And Three Other Gates Measured Less Than They Said

# status: fixed — a fresh schema and a migrated one are compared column by column; coverage, the integration job and mypy now measure what they claim

# reported problem
A review of the test gates found that several of them reported green on less than their names
promised:

- `tests/integration/test_schema.py` only checked that a hand-kept list of tables existed. The list
  missed about twenty tables the code creates and reads (`channels`, `library_track_channels`,
  `feeds_snapshot`, `feeds_profile_exclusions`, `rules_festivals*`, `rules_artists`,
  `rules_artist_proposals`, `rules_genre_proposals`, `rules_podcasts*`, `library_ingestion_records`,
  `rating_tracks`, `tagger_processed_files`, `radio_*`, `news_*`, `crash_reports` and the
  downloader's own tables), and nothing compared columns or indexes at all. Known differences sat in
  plain sight: `db_init.py` declared `rules_ignored_artists` with a plain `INDEX(name)` where
  production has a unique key (`migrate_v22` is written around it), declared five
  `library_track_audio_features` columns production never had (`routers/library.py` documents the
  500 that caused), and added `idx_created_at` / `idx_label_id` / `idx_genre_id` with no migration.
- `scripts/test/music-management-unit.sh` gated on 93% coverage measured with `--cov=services` and
  no omit list. Under `services/` there are about 220 test and fixture files, more lines than the
  source they test, and every one of them counts as fully covered. `tools/`, whose tests run in the
  same job, was not measured. The figure read 95.03%; on source alone it is 84.89%.
- `tests/integration/conftest.py` skipped the whole session when it could not reach the database,
  and `db-integration.sh` gated only on the container reporting healthy — so a database the tests
  could not reach produced a green job that had run nothing.
- `db-integration.sh` ran `mariadb:10.6`; production and `docker/compose.test.yml` run 12.3.
- `./scripts/typecheck.sh --all`, the loose floor every module is supposedly held to, ran in no
  job. Run by hand it did not even start: `tools/muma_mcp/api.py: error: Source file found twice
  under different module names`. `.pylintrc` disables every `missing-*-docstring` check, so AGENTS
  rule 5 was enforced nowhere.

The new drift test, run against develop before any fix (MariaDB 12.3):

```
E       AssertionError: schema bootstrap does not create: ['library_artist_aliases']
E       AssertionError: schema drift between db_init/init_db and the migrations:
E           library_artists: column image_status only in code: {'type': 'varchar(50)', ...}
E           library_artists: column image_updated_at only in code: {'type': 'datetime', ...}
E           library_artists: column primary_image_id only in code: {'type': 'int(11)', ...}
E           library_labels: index fk_labels_parent only in migrations: {'unique': False, 'columns': ['parent_label_id']}
E           library_labels: index parent_label_id only in code: {'unique': False, 'columns': ['parent_label_id']}
E           library_media_files: index idx_media_file_path only in migrations: {'unique': False, 'columns': ['file_path(255)']}
E           library_track_audio_features: index idx_af_file_path only in migrations: {'unique': False, 'columns': ['file_path(255)']}
E           library_track_audio_features: index idx_af_internal_track_id only in migrations: {'unique': False, 'columns': ['internal_track_id']}
E           library_track_audio_features: index internal_track_id only in code: {'unique': False, 'columns': ['internal_track_id']}
E           library_track_ml_labels: index fk_ml_labels_internal_track_id only in migrations: {'unique': False, 'columns': ['internal_track_id']}
E           library_track_ml_labels: index internal_track_id only in code: {'unique': False, 'columns': ['internal_track_id']}
E           rules_genres: index idx_rules_genres_state only in migrations: {'unique': False, 'columns': ['state']}
E           rules_genres: index uq_rules_genres_normalized_name only in migrations: {'unique': True, 'columns': ['normalized_name']}
E       AssertionError: declared by a migration but not created by db_init/init_db: ['library_artist_aliases']
E       AssertionError: init_db never called at startup: ['services.music_manager.rbac', 'services.music_manager.routers.stats']
FAILED tests/integration/test_schema.py::test_every_table_the_code_reads_exists
FAILED tests/integration/test_schema_drift.py::test_a_fresh_stack_and_a_migrated_one_have_the_same_columns_and_indexes
FAILED tests/integration/test_schema_drift.py::test_a_fresh_stack_creates_every_table_a_migration_creates
FAILED tests/integration/test_schema_drift.py::test_every_init_db_is_run_at_startup
```

`library_artist_aliases` is read and written by `routers/curation.py` (the artist edit page) and was
created only by `migrate_v2.sql`, so on a fresh stack — the test stack included — that page had no
table to use.

# Possible reason
Two code paths build this database and nothing compared them. A fresh stack gets its tables from
the CREATE TABLE statements in `services/common/db_init.py` and the routers' `init_db`; production
got its tables long ago and has been moved forward since by the `migrate_*.sql` files. The
integration suite built one schema — db_init, some of the init_dbs, then the migrations on top — and
tested against that, which is the union of both paths and therefore hides a difference between
them. MariaDB names an unnamed index after its column, so a CREATE that did not repeat a migration's
index name produced a second, differently named index; and when a named index is added on a column
a foreign key already covers, InnoDB drops the implicit one, which is why the two paths disagree on
names rather than on coverage.

The other gates had each been set up once and never re-measured: the coverage command predates the
test files that now outnumber the source under `services/`; the skip was written for local runs
without Docker and nobody noticed it also applied in CI; the 10.6 image predates the move to 12.3;
`typecheck.sh --all` was added as a manual command and broke when `tools/muma_mcp` was added.

# solution
- **Schema.** `tests/integration/schema_sources.py` reads every `CREATE TABLE` from the non-test
  Python under `services/` and from the migrations, so the expected-table set cannot fall behind
  the code again. `tests/integration/test_schema_drift.py` builds the schema twice from an empty
  database — once from db_init plus every `init_db` that `main.py`'s startup calls (read from the
  startup function itself) plus the tagger's own table, once from db_init plus every migration
  applied twice — and diffs `information_schema.columns` (type, nullability, default, extra,
  collation) and `information_schema.statistics` (index name, columns with prefix length,
  uniqueness) for every table both create. It also fails on a table only a migration creates, on an
  `init_db` the startup never calls, and on a templated table name it cannot resolve.
  `db-integration.sh` grants the test user `muma_test_*` databases for the two builds.
- **Fixes the test found or the review listed.** `db_init.py` now creates `library_artist_aliases`,
  names its indexes and foreign keys the way the migrations did (`fk_labels_parent`,
  `idx_media_file_path`, `idx_af_file_path`, `idx_af_internal_track_id`,
  `fk_audio_features_internal_track_id`, `fk_ml_labels_internal_track_id`,
  `uq_rules_genres_normalized_name`, `idx_rules_genres_state`), declares `rules_ignored_artists.name`
  unique, and no longer declares the five unused audio-feature columns. `migrate_v36_schema_drift.sql`
  removes duplicate ignored-artist rows (newest kept) and makes the name unique where it is not,
  drops the five columns where they exist (conditionally, so production's table is never rebuilt),
  declares `idx_genre_id` / `idx_label_id` / `idx_created_at`, and declares the three portrait
  columns `artist_images.init_db` adds. The five columns were dropped rather than added to
  production because nothing writes them (the ml-analyzer fills tempo, the spectral features and
  the MFCCs) and nothing reads them since `/library/advanced` stopped selecting them.
- **Coverage.** `[tool.coverage.run]` in `pyproject.toml` omits `*Test.py`, `*/tests/*`,
  `*/test_*.py`, `*/conftest.py` and `mock_base.py`, and the script adds `--cov=tools`.
  `COVERAGE_MIN` moves from 93 to 84 — the one time that floor has gone down, because the old
  figure counted tests as covered code, not because coverage fell. The Cobertura paths are now
  rooted per file (`services/...` or `tools/...`) instead of prefixing everything with `services/`.
- **Integration job.** With `CI` set, an unreachable database, a missing `pymysql` or a scratch
  database that cannot be created fails the session instead of skipping it; locally it still skips,
  with a reason that says the suite did not run.
- **MariaDB version.** `MARIADB_VERSION` defaults to 12.3; `MARIADB_VERSION=10.6
  ./scripts/test/db-integration.sh` still runs the old server, which is the only one that
  reproduces bug report 039's implicit `ON UPDATE`. The suite passes on both.
- **Type checking and docstrings.** `typecheck.sh --all` runs with `--explicit-package-bases` and
  is a new `backend:typecheck-all` job, `allow_failure` while its 299 errors are worked down
  ([open-work](../open-work.md)). `scripts/lint.sh` fails a module on the strict type-check list
  that has an undocumented public function or class; the 80 that had one are documented.

Still open, in [open-work](../open-work.md): the drift test cannot see a difference that exists
only in production's older tables, because both of its paths start from the same `db_init.py`.
The `rules_ignored_artists` unique key and the absent audio columns rest on what the code and the
migrations say about production, not on a query against it.
