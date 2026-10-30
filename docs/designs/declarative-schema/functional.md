# Declarative Schema: Functional Design

## Overview

The database schema has two sources today. `services/common/db_init.py` and the routers' `init_db`
create a fresh database. The 61 `migrate_*.sql` files in the repository root change an existing
one, and every deploy applies them. A schema change needs an edit in both places, and
`test_schema_drift.py` checks that the two give the same result.

That check does not cover production. On 2026-10-29 a read-only comparison of production with a
fresh database from the init found 516 differences: other collations, other primary keys, 7 tables
and 9 columns that exist only in production, 3 foreign keys that exist only in production. The
production ledger (`schema_migrations`) has all 61 files, each with the sha256 of the repository
copy, so no migration is waiting. The differences come from changes made before the ledger, by
hand or by code that no longer exists.

This design removes the migration files. The declarations in the code become the one source. At
each deploy a reconcile step compares them with the live database, and adds what is missing:
tables, columns and indexes. It never drops, renames or narrows. It reports every other
difference. A change that the reconcile cannot do, such as a rename or a data repair, is a
separate script that a person runs with a backup.

## User Stories

- As the developer, I want one place to declare a table, so that a schema change is one edit.
- As the developer, I want a new local database from the init to equal production, so that the
  tests and the local stack run against the real shape.
- As the operator, I want a deploy to add a new column without a migration file, so that I do not
  keep a ledger of 61 files that have all run.
- As the operator, I want a deploy never to drop or change data by itself, so that a wrong
  declaration cannot destroy production data.

## Functional Flows

| Situation | Observable outcome |
|---|---|
| A developer adds a table or a column to a `CREATE TABLE` | The next deploy creates it on production before the new containers start. |
| A developer adds an index | The next deploy creates it. A unique index that the data violates stops the deploy with the table and index name. |
| A developer changes a column type, a primary key or removes a column | CI fails: the declaration no longer matches the production snapshot. The developer writes a one-off script, runs it with a backup, and updates the snapshot. |
| Production has a table, column or index that the code does not declare | The deploy log lists it as "extra". Nothing is dropped. |
| A new installation (local, CI, a self-hoster) | The init creates every table with the production shape, plus the seed data (genres, festivals, permissions and the others). |
| An existing installation that is several releases behind | The deploy adds the missing tables, columns and indexes. Data repairs that old migrations did are not repeated (see Open Questions). |

## Acceptance Criteria

1. The repository has no `migrate_*.sql` file and no `tools/apply_migrations.py`.
2. A fresh database from the init has the same tables, columns, types, keys, indexes, foreign keys
   and collations as the committed production snapshot. The only allowed difference is a list in
   the test, with a reason per entry.
3. The fresh database has the same seed rows as the migrations gave before: 33 genres, 92
   festivals, 118 festival aliases, the roles, permissions, radio channels and news sources.
4. A deploy against production with no schema change in the code changes nothing and logs
   "schema in sync" plus the list of extra objects.
5. A deploy after a new column in the code adds that column, and only that.
6. No deploy step drops, renames or changes the type of anything.

## Decisions

Teun decided these on 2026-10-29 (issue #43):

- Which side is the truth per drift item: production, except where the code adds something. The
  table is in [technical.md, Drift Decisions](technical.md#drift-decisions).
- The 6 unused production-only tables are dropped in a cleanup script with a backup.
  `library_track_ml_predictions` is declared, so the deprecated ml-analyzer keeps its table.
- The 6 unused production-only columns are dropped in the same script.
- The foreign key `scrobble_listens.track_id` to `library_tracks` changes from `ON DELETE CASCADE`
  to `ON DELETE SET NULL`, and the code declares it. A deleted track row no longer takes its
  listen history with it.
- An installation must run 0.93.x (the last release with migrations) before it upgrades past this
  change. The changelog says so under "Breaking", and `docs/self-hosting.md` too.
