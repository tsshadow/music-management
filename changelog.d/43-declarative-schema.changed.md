- **Breaking for self-hosters: upgrade through 0.93.x first.** The 61 `migrate_*.sql` files and
  `tools/apply_migrations.py` are gone. An installation older than 0.93.0 must deploy a 0.93.x
  release before this one, or its database misses the columns those files added.
- **The schema is declared once, and each deploy adds what the database lacks.** Every table and
  view is in `services/common/schema_tables.py`, in the shape production has, and the seed rows a
  new database needs are in `services/common/seeds/`. Deploy step 4 runs the new `schema-reconcile`
  one-shot from the image it deploys: it builds the declaration in a scratch database, adds the
  missing tables, columns, indexes and views, and prints every other difference as a `report:`
  line without changing it. A fresh database now equals production, which the integration suite
  checks against a snapshot of production's schema (`tests/integration/schema/production.tsv`).
  Refs #43.
- **`tools/schema_cleanup_2026_11.py` removes what production has and nothing reads.** Six tables
  (the two download queues, `rules_genres_new`/`_old`, the two broken-song tables) and six columns
  go, a listen keeps its row when its track is deleted (`ON DELETE SET NULL` in place of
  `CASCADE`), and `rules_genres.canonical_id` gets its foreign key. A dry run by default; `--apply`
  dumps the database first. Run it once after this release.

<!-- release notes -->

- **Upgrade through 0.93.x first.** The database schema is now declared in one place, and each
  deploy adds what is missing. An installation older than 0.93.0 must deploy 0.93.x before this
  release.
