- **A fresh database and production's disagreed about the schema, and no test compared them.** A
  new integration test builds the schema twice from nothing — once the way a fresh stack does
  (`db_init.py` plus every `init_db`), once the way a deploy does (the migrations) — and compares
  every column and index. On develop it found `library_artist_aliases`, which the artist edit page
  reads, missing from every fresh stack, three portrait columns no migration declared, and seven
  indexes that were missing or named differently on one of the two paths. `migrate_v36_schema_drift.sql` also gives
  `rules_ignored_artists.name` the unique key production already has (removing duplicates first),
  drops five audio-feature columns only fresh stacks ever had and nothing reads or writes, and
  declares three indexes that existed only in `db_init.py`. Bug report 047.

<!-- release notes -->
- A new installation now gets exactly the database layout production has; the artist edit page no
  longer fails on a fresh install.
