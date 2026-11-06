# LMS had nothing in its schema stopping a second user that differs only in case

# status: fixed

# reported problem

Bug report 074: a login typed `Teun` for the account `user` made LMS create a second user,
id 13, beside user 1. The fix made `User::find(session, loginName)` compare with
`COLLATE NOCASE`, so no code path creates such a user any more. But the database itself still
accepted one: the `user` table had no index on `login_name` at all, unique or otherwise. Any
future code path that inserts a user without going through `User::find()` first, or a write from
outside LMS (music-manager writes `lms.db` directly), could fork an account again, and nothing
would say so.

The index was left out of 074 on purpose. A versioned migration that adds it fails on a database
that still holds the fork, a failed migration throws, and LMS then does not start. The fork on
production was merged by `repair-username-case.sh` on 2026-09-25 (GitLab issue #17).

Measured read-only on production on 2026-09-26, `/docker/lms/var/lms/lms.db` (the `lms`
container's `/var/lms`): `db_version` 123, 12 users, no index on `user`, and
`SELECT lower(login_name), COUNT(*) FROM user GROUP BY 1 HAVING COUNT(*) > 1` returns no rows.

# Possible reason

Upstream LMS matches login names exactly and never needed the index. The fork's case-insensitive
lookup (074) closed the code path but not the schema.

# solution

LMS schema version 124 (`migrateFromV123` in
`services/music-management-server/src/libs/database/impl/Migration.cpp`) creates

    CREATE UNIQUE INDEX user_login_name_nocase_unique_idx ON user(login_name COLLATE NOCASE)

- **`COLLATE NOCASE`, not `lower(login_name)`.** The lookup is `login_name = ? COLLATE NOCASE`.
  SQLite only uses an expression index when the query repeats the expression, so an index on
  `lower(login_name)` would enforce uniqueness but never serve the lookup. With the collation
  index `EXPLAIN QUERY PLAN` shows `SEARCH u USING INDEX user_login_name_nocase_unique_idx
  (login_name=?)`. Both fold ASCII only, so they refuse exactly the same pairs. The existing
  schema already uses this style (`artist_sort_name_nocase_idx`, `directory_name_idx`).
- **A database that still holds a case variant keeps starting.** The step first looks for login
  names that differ only in case. If it finds any it logs an `ERROR` naming them and the repair
  script, skips the index, and the migration completes (the version still moves to 124). Aborting
  would take the whole server down over a condition LMS already handles: `User::find()` picks the
  MuMa-linked variant, then the oldest, and never throws on two rows. `NULL` login names are not
  counted, since a unique index allows any number of them.
- **Retried on every start.** `Session::createIndexesIfNeeded()`, which runs on every start and
  is what builds a fresh database's indexes, calls the same helper
  (`Migration::createUserLoginNameUniqueIndexIfPossible`). A fresh database gets the index there,
  and a database that skipped it gets it on the first start after the variants are merged. No
  second migration is needed. The error repeats on every start until then, which is deliberate.
- Tests: `Database.migration` (index created, then the fork case: migration completes with the
  index skipped and all users kept, then the index appears once the variant is gone and refuses a
  case-variant rename) and `DatabaseFixture.User_loginNameIsUniqueIgnoringCase` (a fresh schema
  has the index). The two 074 tests that set up a fork (`User_findByLoginNamePrefersTheMumaLinkedVariant`,
  `CaseInsensitiveLogin.anExistingForkNoLongerReceivesTheLogin`) now drop the index for their
  duration through `ScopedNoLoginNameUniqueIndex`. They still cover a database where the index had
  to be skipped.
