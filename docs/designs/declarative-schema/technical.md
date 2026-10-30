# Declarative Schema: Technical Design

Implements [functional.md](functional.md).

## Data Model

### What is measured

Read-only, against production on 2026-10-29 (MariaDB 13.0.2, database `music-management`):

- `schema_migrations` has all 61 `migrate_*.sql` files, each with the sha256 of the repository copy.
- A fresh database from the init (`ensure_tables_exist()` plus every router's `init_db`) differs from
  production in 516 places. After the collation and foreign-key-name noise is removed, 64 remain.
  They are in [Drift Decisions](#drift-decisions).
- `test_schema_drift.py` passes: the init and "init plus all migrations" give the same schema. It
  never compares with production, so it did not see any of the 64.

### One source: `services/common/schema_tables.py`

Every table and view of the shared database is declared once, in
`services/common/schema_tables.py`: `TABLES` holds `(name, CREATE TABLE IF NOT EXISTS ...)` pairs
in the order to create them, `VIEWS` the two views. `db_init.create_tables()` runs them, and the
reconcile builds its probe from them. The routers' `init_db` keep only their data (roles,
permissions, radio channels, news sources). `tests/integration/test_schema.py` fails on a
`CREATE TABLE` in any other file under `services/`.

Every statement is the shape production has, with an explicit table option:

```sql
) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_general_ci
```

Production has `utf8mb4_general_ci` on 83 tables and 263 columns. A fresh MariaDB 13 server gives
`utf8mb4_uca1400_ai_ci` when nothing is named, so a local database and production sort and compare
text differently without the pin. A change to `uca1400` is a rebuild of every text column and is
out of scope.

### Seeds move into the init

Today these rows exist only because a migration inserted them. They move to
`services/common/db_seeds.py`, which the init calls after the tables exist. Every insert is
`INSERT IGNORE` on the table's unique key, so a second run changes nothing and a curator's edit
stays.

| Table | Rows | Today from |
|---|---|---|
| `rules_genres` | 33 | migrations |
| `rules_festivals` | 92 | migrations |
| `rules_festival_aliases` | 118 | migrations |
| `rules_label_name_choices` | 104 | migrations |
| `rules_artists` (legacy redirect black list) | 11 | migrations |
| `rules_ignored_artists` | 11 | migrations |
| `rules_scene_group_date_format` | 5 | migrations |
| `roles`, `permissions`, `role_permissions`, `radio_channels`, `news_sources` | as today | router `init_db`, unchanged |

The 17 migrations that repaired data (v3, v4, v6, v7_festivals, v7_youtube_category_genres, v10,
v14, v22_promo, v26, v30, v32, v36, v40, v45, v54, v56, v57) ran on production and fix rows that a
new installation never has. They are deleted, not moved.

### The reconcile

`services/common/schema_reconcile.py`, run as `python -m services.common.schema_reconcile`.

1. Build the declared schema in a scratch database `<db>_schema_probe`: drop it, create it, run every
   `CREATE TABLE` there. MariaDB parses the SQL, so the reconcile needs no SQL parser of its own.
2. Read `information_schema` for both databases: tables, columns (type, nullability, default,
   extra, collation), indexes (columns, uniqueness), foreign keys (columns, referenced table and
   columns, `ON DELETE`, `ON UPDATE`). Indexes and foreign keys are compared by their content, not
   their name.
3. Act on the difference:

| Difference | Action |
|---|---|
| Table declared, missing live | `SHOW CREATE TABLE` from the probe, run it live. |
| Column declared, missing live | `ALTER TABLE ... ADD COLUMN` with the probe's definition, `AFTER` the probe's previous column. |
| Index declared, missing live | `ALTER TABLE ... ADD [UNIQUE] INDEX` with the probe's name. A duplicate-key error stops the run and names the table and index. |
| Foreign key declared, missing live | Report only. An orphan row makes the `ADD` fail, so a new foreign key is a script. |
| Live table, column, index or foreign key not declared | Report as "extra". |
| Type, nullability, default, collation or primary key differs | Report as "changed". |

4. Drop the probe database. Print one line per action and per reported item, then
   `schema in sync`, `schema reconciled: N changes, M reported`, or with `--dry-run` `dry run, schema not changed: N changes, M reported`.

Every statement runs with `lock_wait_timeout` and `innodb_lock_wait_timeout` set, the same as
`apply_migrations.py` does today (bug report 068). `--dry-run` prints the statements and runs none.
The deploy runs it as the database root user (`MYSQL_ROOT_PASSWORD` from the env file, which
reaches compose on stdin), so it can create and drop the probe. `--snapshot` prints the live
schema in the format of `production.tsv` and changes nothing.

### Drift Decisions

Rule: production runs, so its shape is the truth. The declaration changes to match it. Where the
code is better and the change is an addition, the reconcile adds it to production. Teun decided
the open items on 2026-10-29 (issue #43).

| Item | Production | Code | Proposal |
|---|---|---|---|
| Collation, 83 tables, 263 columns | `utf8mb4_general_ci` | server default | Pin `utf8mb4_general_ci` in every declaration. |
| 40 `TIMESTAMP` columns | `NOT NULL` | `NULL` | Declare `NOT NULL` (a MariaDB 10.6 effect production kept). |
| Foreign key names | `channels_ibfk_1` and similar | `1` and similar | Ignore: the reconcile compares content. |
| `downloads_soundcloud_queue` (1348 rows), `downloads_youtube_queue` (724) | exists | absent, no code reads it | Drop in the cleanup script (decided 2026-10-29). |
| `rules_genres_new` (246), `rules_genres_old` (233) | exists | absent, no code reads it | Drop in the cleanup script (decided). |
| `library_broken_songs` (0), `library_broken_song_artist_lookup` (21) | exists | absent; `BrokenSongHelper` wrote a row on a failed tag that nothing read, `BrokenSongArtistLookupHelper` was never called | Drop the tables and both helpers (decided). The tagger's failure count (`record_failure`) already keeps the failure. |
| `library_track_ml_predictions` (0) | exists | read by the deprecated ml-analyzer | Declare it, so ml-analyzer keeps a table. |
| `downloads_soundcloud_archive` unique `(account, video_id)` | exists | two plain indexes | Declare the unique index. Without it a fresh database records a download twice. |
| `downloads_youtube_archive` primary key | `(video_id, download_type)`, `video_id VARCHAR(32)`, `filename`/`title`/`url VARCHAR(255) NOT NULL` | `id` auto-increment, `TEXT` | Declare the production shape. |
| `downloads_soundcloud_accounts.soundcloud_id` | `BIGINT` | `VARCHAR(255)` | Declare `BIGINT`. |
| `downloads_youtube_accounts.channel_id` | `TEXT` | `VARCHAR(255)` | Declare `TEXT`. |
| `downloads_soundcloud_accounts.account_type`, `image_enrichment_hint`, `linked_artist_id` | exists | no code reads them | Drop in the cleanup script (decided). |
| `artist_external_ids` | primary key `id`, unique `(artist_id, source, external_id)`, `confidence` | primary key `(artist_id, source)` | Declare the production shape without `confidence`, which the cleanup script drops. Production allows two ids per source; the code shape does not. |
| `library_track_audio_features`, `library_track_ml_labels` | primary key `id`, unique or plain `track_id`, foreign key to `library_tracks` `SET NULL` | primary key `track_id` | Declare the production shape. |
| `library_artist_images` | `status`, `error_message`, `NOT NULL` on `cached_path` and `source`, `mime_type VARCHAR(100)`, unique `(artist_id, source, source_id)` | without them | Declare the production shape. The two extra columns `status` and `error_message`, and `artist_external_ids.confidence`: drop in the cleanup script (decided). |
| `library_artists.created_at`, `library_labels.created_at` | absent | declared | The reconcile adds them. |
| `rules_genres.canonical_id` index and self foreign key `SET NULL` | absent | declared | Index: the reconcile adds it. Foreign key: the cleanup script adds it after it clears orphans. |
| `scrobble_listens.track_id` foreign key `ON DELETE CASCADE` | exists | absent | Change to `ON DELETE SET NULL` and declare it (decided). The listen stays when its track row goes; `track_id` is already nullable. |
| `scrobble_listens` index `idx_listens_match_method`, `scrobble_unmatched_listens` index `idx_unmatched_retry`, `rules_catid_label` unique `catid` | exists | absent | Declare them. |
| `rules_ignored_artists` unique `name` | named `idx_ignored_name` | named `name` | Declare the production name. |

### The cleanup script

`scripts/prod/` is outside this repository, so the one-off goes to `tools/schema_cleanup_2026_11.py`
with `--dry-run` as default. It dumps every table it changes with `tools/db_backup.py` first, then
drops the tables and columns marked "drop" above, replaces the `scrobble_listens` foreign key with
one that has `ON DELETE SET NULL`, and adds the `rules_genres` foreign key. Teun runs it once after the release. Until it runs, the reconcile
reports those objects as "extra" and nothing breaks.

### The production snapshot

`tests/integration/schema/production.tsv` is the output of the `information_schema` queries from
step 2 against production, one object per line, sorted. Table, column, index and constraint names
only: no rows, no hosts. `python -m services.common.schema_reconcile --snapshot` writes it,
read-only. It is refreshed after each release that changes the schema.

## API Contract

No endpoint changes.

| Endpoint | Request | Response | Error cases |
|---|---|---|---|
| none | | | |

## Cross-App Impact

- `scripts/deploy.sh`, step d: replaces `apply_migrations.py` with the `schema-reconcile` one-shot
  in `docker/docker-compose.yml`, run before `up`:
  `docker-compose run --rm --no-deps -T schema-reconcile --lock-wait-timeout 120`. Its image is the
  core image at `SCHEMA_IMAGE_TAG` (the `IMAGE_TAG` being deployed, else `VERSION`), so the new
  release's declaration runs while the old containers still serve. The reconcile only adds, so the
  expand-only rule holds without a test of its own. A failure stops the deploy before `up`, as
  before. `up` always skips the service.
- `schema_migrations` stays in production, unread, as a record. A later cleanup may drop it.
- `scripts/lib/e2e-stack.sh` applied every migration to seed `rules_genres`. The stack's init seeds
  it now, and the script runs the reconcile in the music-manager container and requires
  `schema in sync, 0 reported`.
- `services/ml-analyzer`, the downloader and the importer: no change. They read the same tables.
- `docs/self-hosting.md`, `AGENTS.md` (Testing & Stability, the schema-change paragraph) and
  `CONTRIBUTING.md`: the "two edits" rule becomes "one edit; a change the reconcile cannot do needs
  a script and a snapshot refresh".
- Removed: the 61 `migrate_*.sql`, `tools/apply_migrations.py` and its tests,
  `tests/ci/test_migration_ordering.py`, `test_schema_drift.py`, `test_migration_ledger.py`, the
  `BrokenSong*Helper` classes, the `!migrate_*.sql` exception in `.gitignore`, and the
  `migrate_*.sql` exemption in `scripts/ci/public-check.sh`.

**Upgrade path, breaking for self-hosters.** An installation must run 0.93.x, or any release that
still has the migrations, before it upgrades past this change. The changelog says so under
"Breaking".

## Technical Acceptance Criteria

1. `tests/integration/test_schema_snapshot.py`: a fresh database from the init equals
   `production.tsv`, except the differences it lists, each with a reason. Run in
   `backend:integration`.
2. The same test fails, and names the object, when a declaration changes a type, a primary key or
   drops a column.
3. `schema_reconcile` against the fresh database reports `schema in sync` and runs no statement.
4. `schema_reconcile` against a fresh database with one column, one index and one table dropped
   adds back exactly those three, and a second run changes nothing.
5. `schema_reconcile` against a database with an extra table, an extra column and a changed type
   reports all three and changes none of them.
6. A unique index the data violates stops the run with exit code 1 and the table and index name.
7. `db_seeds` against a fresh database gives the row counts in the seed table above; a second run
   inserts nothing; a changed seed row stays changed.
8. `--dry-run` against production prints only the additions from the Drift Decisions table and the
   reported items, and changes nothing.
9. No script, compose file, CI job or test reads a `migrate_*.sql` file. Comments that name one as
   history stay.

## Related Docs

- [db-transactions](../db-transactions/technical.md)
- `docs/bug-reports/021-genre-migration-never-shipped.md`
- `docs/bug-reports/068-deploy-hangs-on-no-op-alter-metadata-lock.md`
- `docs/self-hosting.md#schema-changes`
