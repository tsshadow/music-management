# The LMS listen reconcile answered 500 on production because of a stale second lms.db

# status: fixed

# reported problem

On 2026-09-25, right after 0.73.1 went live, the first dry run of the LMS listen reconcile
(`GET /api/scrobble/reconcile/lms`, shipped in MR !940) answered `500 Internal Server Error`
every time. The traceback ended in `read_lms_listens`:

```
sqlite3.OperationalError: no such table: user
```

# Possible reason

`lms_db_targets()` hands the reconcile every LMS database music-manager can see under
`/app/data/*/lms.db`. On production that is two files:

- `/app/data/stable/lms.db`: the live server, with the `listen`, `user` and `track` tables.
- `/app/data/alpha/lms.db`: a leftover at LMS schema version 114. It has `listen` and `track`,
  but no `user` table, and no alpha container runs any more. The file was last written on
  2026-09-24.

`open_servers` opened each file without checking it, and `LMS_LISTENS_SQL` joins `user`. So the
one stale file failed the whole request, including the part for the live server.

# solution

`open_servers` now checks each database for the tables the listen query joins
(`LMS_REQUIRED_TABLES`: `listen`, `user`, `track`). If one is missing, it logs a WARNING that
names the file and the missing tables, closes the file and skips it. The reconcile then runs
against the databases that can answer. `OpenServersTest` in
`services/music_manager/tests/test_scrobble_reconcile.py` covers a skipped stale file, two
complete files, and the missing-table helper.

Whether `alpha/lms.db` should be deleted from production is a separate decision. It is no longer
needed for the reconcile to work.
